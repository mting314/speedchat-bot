import discord
from discord.ext import tasks
import json
import urllib.parse as urlparse
from urllib.parse import urlencode
import requests
import re
from bs4 import BeautifulSoup
import os

import asyncio
from pyppeteer import launch

from constants import *
from perms import *

# Assumptions: class number is always either 001,002, etc., or '%'
regex = 'Iwe_ClassSearch_SearchResults.AddToCourseData\("[\d_]*?%s[\d]{0,3}",({"Term":"%s".*?"ClassNumber":" *?[\d%%]{1,3} *.*?"Path":"[\d_]*?%s[\d]{0,3}".*?"Token":".*?"})\);'
HEADERS = {"X-Requested-With": "XMLHttpRequest"}
filter_flags = '{"enrollment_status":"O,W,C,X,T,S","advanced":"y","meet_days":"M,T,W,R,F","start_time":"8:00 am","end_time":"7:00 pm","meet_locations":null,"meet_units":null,"instructor":null,"class_career":null,"impacted":null,"enrollment_restrictions":null,"enforced_requisites":null,"individual_studies":null,"summer_session":null}'



def _parse_string_to_array(tag):
    """
    Takes a string of HTML that displays locations, times, etc. from UCLA course details page, and separates into
    an array based on the <br/> tags.
    """
    if tag is None:
        return []

    my_string = ''.join(map(str, tag.contents))
    tagMatcher = re.compile('<wbr/>|<(/)?p>|<(/)?a[^>]*>')
    text = tagMatcher.sub('', my_string).strip()
    arr = text.split("<br/>")
    return arr


def _generate_url(base_url, params):
    """
    Generate a URL given many parameters to attach as query strings. Also replaces single quote with double quote
    because that's what UCLA likes.
    """
    url_parts = list(urlparse.urlparse(base_url))
    query = dict(urlparse.parse_qsl(url_parts[4]))
    query.update(params)

    url_parts[4] = urlencode(query)

    final_url = urlparse.urlunparse(url_parts).replace("%27", "%22")
    return final_url


def parse_catalog_no(catalog):
    """
    
    catalog: String of the class's number, i.e. 61 or 131AH or M120
    
    """
    match = re.match(r"([0-9]+)([a-zA-Z]+)", catalog, re.I)
    if match:
        return f'{match[1]:>04s}' + match[2]
    else:
        return f'{catalog:>04s}'


def parse_class_id(html):
    """
    Given html from GetCourseSummary endpoint, extract the class number. Uses assumption that class number is
    always the first 9 digits of a certain div
    """
    id_regex = '<div class="row-fluid data_row primary-row class-info class-not-checked" id="([\d]{9})_'
    match = re.search(id_regex, str(html))
    return match[1] if match else None


# Commands for looking up UCLA classes
class UCLA(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Regexes (regexi?) to catch all the different cases for the enrollment statuses of a class
        # also contain named capture groups so it's easy to pick up capacity vs count
        self.status_regexes = {
            "tenative": re.compile('^Tenative'),
            "cancelled": re.compile('^Cancelled'),
            "closedByDept": re.compile(
                '^Closed by Dept[a-zA-Z,/ ]*(\((?P<Capacity>\d+) capacity, (?P<EnrolledCount>\d+) enrolled, (?P<WaitlistedCount>\d+) waitlisted\))?'),
            "classFull": re.compile(
                'ClosedClass Full \((?P<Capacity>\d+)\)(, Over Enrolled By (?P<OverenrolledCount>\d+))?'),
            "classOpen": re.compile('Open(?P<EnrolledCount>\d+) of (?P<Capacity>\d+) Enrolled(\d+) Spots? Left'),
            "waitlistOnly": re.compile('^Waitlist$'),
            "waitlistFull": re.compile(
                '^WaitlistClass Full \((?P<Capacity>\d+)\)(, Over Enrolled By (?P<OverenrolledCount>\d+))?'),
        }
        # Waitlist regexes
        self.waitlist_regexes = {
            "waitlistOpen": re.compile('(?P<WaitlistCount>\d+) of (?P<WaitlistCapacity>\d+) Taken'),
            "noWaitlist": re.compile('No Waitlist'),
            "waitlistClosed": re.compile('Waitlist Full \((?P<WaitlistCapacity>\d+)\)'),
        }

        # The main urls we'll be scraping from
        self.PUBLIC_RESULTS_URL     = "https://sa.ucla.edu/ro/Public/SOC/Results"
        self.GET_COURSE_SUMMARY_URL = "https://sa.ucla.edu/ro/Public/SOC/Results/GetCourseSummary"
        self.COURSE_TITLES_VIEW     = "https://sa.ucla.edu/ro/Public/SOC/Results/CourseTitlesView"

        self.term = "21W"
        self.data_dir = f"speedchat_bot/ucla_data/{self.term}"
        self._reload_classes()
        
    
    def _search_for_class_model(self, subject, catalog):
        """
        Finds the model for each class that matches subject+catalog, and also attaches the "human readable" class name.

        subject: String of the class's subject in CAPS format, i.e. (MATH or COM SCI)
        catalog: String of the class's number, i.e. 61 or 131AH or M120

        returns a generator of tuples (class's "human readable name", model) that match the given subject + catalog
        e.g. (Mathematics (MATH) 19 - COVID-19: Patterns and Predictions in Art, {\"Term\":\"21W\",\"SubjectAreaCode\":\"MATH...)
        
        """
        with open(self.data_dir + "/class_names.json") as fp:
            # TODO: Maybe separate subjects into their own json?
            data = json.load(fp)['class_names']
            classes_in_subject = data[subject]
            for my_class in classes_in_subject:
                if my_class[0].split()[0] == str(catalog):
                    yield f"{subject} {my_class[0]}", my_class[1]



    def _generate_embed(self, parsed_class, letter_choice=None):
        """Build a Discord Embed message based on a class dictionary, for sending in a fast mode"""
        title = '{choice} {class_name}'.format(choice=f"(Choice {letter_choice})" if letter_choice else '',
                                               class_name=parsed_class["class_name"])

        embedVar = discord.Embed(title=title, description=f'[{parsed_class["section_name"]}]({parsed_class["url"]})',
                                 color=0x00ff00)
        embedVar.add_field(name="Term", value=parsed_class["term"], inline=True)
        embedVar.add_field(name="Times", value=parsed_class["times"], inline=True)
        embedVar.add_field(name="Days", value=parsed_class["days"], inline=True)
        embedVar.add_field(name="Locations", value=parsed_class["locations"], inline=True)

        embedVar.add_field(name="Enrollment Status",
                           value=f'{parsed_class["enrollment_status"]} ({parsed_class["enrollment_count"]}/{parsed_class["enrollment_capacity"]} enrolled)',
                           inline=True)
        if "waitlist_status" in parsed_class:
            embedVar.add_field(name="Waitlist Status",
                               value=f'{parsed_class["waitlist_status"]} ({parsed_class["waitlist_count"]}/{parsed_class["waitlist_capacity"]} taken)',
                               inline=True)
        else:
            embedVar.add_field(name="Waitlist Status", value='Unable to parse', inline=True)

        if "description" in parsed_class:
            embedVar.add_field(name="Course Description", value=parsed_class['description'], inline=False)

        return embedVar

    async def _generate_image(self, browser, class_id, ctx, letter_choice=None):
        """Take a picture of a class id's details page, for sending in a slow mode"""

        if os.path.exists("candidate.png"):
            os.remove("candidate.png")

        params = {'t': self.term, 'sBy': 'classidnumber', 'id': class_id}
        final_url = _generate_url(self.PUBLIC_RESULTS_URL, params)

        page = await browser.newPage()

        await page.goto(final_url)

        await page.waitForSelector('#resultsTitle')
        element = await page.querySelector('#resultsTitle')

        if letter_choice:
            await page.evaluate(f'document.querySelector("a[id$=\'-title\']").prepend("(Choice {letter_choice}) ")')

        await element.screenshot(path='candidate.png')
        if letter_choice:
            await ctx.channel.send(f"Choice {letter_choice}", file=discord.File('candidate.png'))
        else:
            await ctx.channel.send(file=discord.File('candidate.png'))

        if os.path.exists("candidate.png"):
            os.remove("candidate.png")

    @commands.command(help="Switch to a new term for searching (i.e. to 20F)")
    async def switch_term(self, ctx, new_term: str):
        # First, is this the right format?
        template = re.compile('[\d]{2}[FWS]{1}')  # i.e. 20F
        if template.match(new_term) is None:
            ctx.channel.send(f"Sorry, {new_term} looks like a malformed term.")
            return

        if self.term and self.term is new_term:
            ctx.channel.send(f"You're already on {self.term}!")
            return

        # If we pass the checks, actually switch term, and initialize class list
        self.term = new_term
        self._reload_classes()

    @commands.command(help="Search for a class in preparation to add to watch list")    
    async def reload_classes(self, ctx):
        self._reload_classes()



    def _reload_classes(self):
        # Load list of subjects parsed from UCLA website
        # TODO: programatically get subjects.json
        f = open(self.data_dir + "/subjects.json")
        self.subjectsJSON = json.load(f)
        f.close()


        if os.path.exists(self.data_dir + "/class_names.json"):
            with open(self.data_dir + "/class_names.json") as fp:
                data = json.load(fp)
                if data["term"] == self.term:  # no need to update json
                    return

        class_name_dict = {}
        for subject in self.subjectsJSON:
            pageNumber = 1
            # Replace everything but spaces, which get changed to "+", i.e. "ART HIS" -> "ART+HIS"
            model = {"subj_area_cd":subject["value"],"search_by":"subject","term_cd":self.term,"SubjectAreaName":"Computer Science (COM SCI)","CrsCatlgName":"Enter a Catalog Number or Class Title (Optional)","ActiveEnrollmentFlag":"n","HasData":"True"}
            all_classes = []
            while True:
                params = {'search_by': 'subject', 'model': model, "pageNumber":pageNumber, 'FilterFlags': filter_flags, '_': '1571869764769'}

                url = _generate_url(self.COURSE_TITLES_VIEW, params)

                # old_url = f'https://sa.ucla.edu/ro/Public/SOC/Results/CourseTitlesView?search_by=subject&model=%7B%22subj_area_cd%22%3A%22{subject_name}%22%2C%22search_by%22%3A%22Subject%22%2C%22term_cd%22%3A%22{self.term}%22%2C%22SubjectAreaName%22%3A%22Mathematics+(MATH)%22%2C%22CrsCatlgName%22%3A%22Enter+a+Catalog+Number+or+Class+Title+(Optional)%22%2C%22ActiveEnrollmentFlag%22%3A%22n%22%2C%22HasData%22%3A%22True%22%7D&pageNumber={pageNumber}&filterFlags=%7B%22enrollment_status%22%3A%22O%2CW%2CC%2CX%2CT%2CS%22%2C%22advanced%22%3A%22y%22%2C%22meet_days%22%3A%22M%2CT%2CW%2CR%2CF%22%2C%22start_time%22%3A%228%3A00+am%22%2C%22end_time%22%3A%227%3A00+pm%22%2C%22meet_locations%22%3Anull%2C%22meet_units%22%3Anull%2C%22instructor%22%3Anull%2C%22class_career%22%3Anull%2C%22impacted%22%3Anull%2C%22enrollment_restrictions%22%3Anull%2C%22enforced_requisites%22%3Anull%2C%22individual_studies%22%3Anull%2C%22summer_session%22%3Anull%7D'

                # print(url)
                r = requests.get(url, headers=HEADERS)
                soup = BeautifulSoup(r.content, "lxml")
                div_script_pairs = zip(soup.select("h3.head"), soup.select("script"))

                for div, script in div_script_pairs:
                    # I can't guarantee that there isn't some wack scenario where there are two classes
                    # names exactly the same, make each name+model pair like a tuple instead
                    all_classes.append(
                        [div.select_one('a[id$="-title"]').text, re.search("({.*?})", script.decode_contents())[1]])
                # when we get past all the result pages, we'll get nothing from requests.get
                if r.content == b'':
                    break

                pageNumber += 1

            class_name_dict[subject["value"]] = all_classes
            print("loaded", subject["label"])

        class_names_file = open(self.data_dir + "/class_names.json", "w")
        class_names_file.write(
            json.dumps({"term": self.term, "class_names": class_name_dict}, indent=4, sort_keys=True))
        class_names_file.close()
        print("done")

    def _parse_enrollment_status(self, my_string):
        """Go through the dictionary of enrollment regexes, return an enrollment dictionary when the right match is
        found. """

        for potential_status, regex in self.status_regexes.items():
            matches = regex.match(my_string)
            if matches is None:
                continue
            else:
                match_dict = matches.groupdict()
                enrollment_dict = {
                    "enrollment_status": potential_status,
                    # TODO: Is it okay to return 0 
                    "enrollment_capacity": int(match_dict["Capacity"] or 0) if "Capacity" in match_dict else None,
                    "enrollment_count": int(
                        match_dict["EnrolledCount"] or 0) if "EnrolledCount" in match_dict else None,
                    "enrollment_over": int(
                        match_dict["OverenrolledCount"] or 0) if "OverenrolledCount" in match_dict else None,
                }
                # Sometimes the status string doesn't say either the Capacity and or the Count,
                # i.e. "ClosedClass Full (45), Over Enrolled By 3" doesn't give any info on the count
                # but since the class is full, we know that the enrollment count and capacity have to match
                # and are both 45. This implements that logic.
                if enrollment_dict['enrollment_status'] == "classFull" or enrollment_dict[
                    'enrollment_status'] == "waitlistFull":
                    enrollment_dict["enrollment_count"] = enrollment_dict["enrollment_capacity"]
                return enrollment_dict

    def _parseWaitlistData(self, my_string):
        for potential_status, regex in self.waitlist_regexes.items():
            matches = regex.match(my_string)
            if matches is None:
                continue
            else:
                if potential_status == self.waitlist_regexes["noWaitlist"]:
                    return {
                        "waitlist_status": potential_status,
                        "waitlist_capacity": "N/A",
                        "waitlist_count": "N/A",
                    }
                else:
                    match_dict = matches.groupdict()
                    waitlist_dict = {
                        "waitlist_status": potential_status,
                        "waitlist_capacity": int(
                            match_dict["WaitlistCapacity"] or 0) if "WaitlistCapacity" in match_dict else None,
                        "waitlist_count": int(
                            match_dict["WaitlistCount"] or 0) if "WaitlistCount" in match_dict else None,
                    }
                    if waitlist_dict["waitlist_status"] == "waitlistClosed":
                        waitlist_dict["waitlist_count"] = waitlist_dict["waitlist_capacity"]
                    return waitlist_dict

    def _parse_class(self, name_soup_pair, term=None):
        if type(name_soup_pair) is tuple:
            name = name_soup_pair[0]
            soup = name_soup_pair[1]
        else:  # we sent to this function soup from the public records page, which has name info on it
            name = name_soup_pair.select_one("a[id$=-title]").text
            soup = name_soup_pair
        enrollment_data = soup.select_one("div[id$=-status_data]").text
        waitlist_data = soup.select_one("div[id$=-waitlist_data]").text.replace("\n", '')

        locations = _parse_string_to_array(soup.select_one("div[id$=-location_data]"))
        days = _parse_string_to_array(soup.select_one("div[id$=-days_data] p a"))
        times = _parse_string_to_array(soup.select_one("div[id$=-time_data]>p") or None)

        # I hope it always looks lile <div id="blah-units_data"><p> # of units </p></div>
        # could be wrong...
        units = soup.select_one("div[id$=-units_data] p").text

        details_url = "https://sa.ucla.edu" + soup.select_one('a[title^="Class Detail for "]')['href']
        section_name = soup.select_one('a[title^="Class Detail for "]').text
        details_url_parts = dict(urlparse.parse_qsl(list(urlparse.urlparse(details_url))[4]))

        class_dict = {
            "subject": details_url_parts['subj_area_cd'].strip(),
            "class_no": details_url_parts['class_no'].strip(),
            "class_id": parse_class_id(str(soup)),
            "class_name": name,
            "term": term or self.term,
            "section_name": section_name,
            "days": days,
            "times": times,
            "locations": locations,
            "units": units,
            "url": details_url,
            "enrollment_data": enrollment_data,
        }

        # BEGIN PARSING STATUS

        a = self._parse_enrollment_status(enrollment_data) or None
        b = self._parseWaitlistData(waitlist_data) or None

        if a: class_dict = {**class_dict, **a}  # grr if this were python 3.9 we could just use |
        if b: class_dict = {**class_dict, **b}

        # don't need to clean ints, only strings
        return {k: v.replace("\r", '').replace("\n", '').strip() if type(v) == "str" else v for k, v in
                class_dict.items()}

    async def _generate_class_view(self, ctx, subject: str, catalog: str, mode="slow", display_description=False, choices=False):
        """
        Given the lookup info of subject+catalog (i.e. MATH+151AH), send either embeds or images based
        on the resulting soups (from GetCourseSummary). Returns that lsit of name_soup_pairs.
        """
        model_choices = list(self._search_for_class_model(subject, catalog))

        htmls = []
        for name_model_pair in model_choices:
            print(name_model_pair[1])
            htmls = htmls + self.check_class(name_model_pair)

        # htmls = [chr(i+65): htmls[i] for i in range(len(htmls))}

        # I can't decide how this ought to be designed (idk anything about UX), but this is how it's gonna work:
        # there are two modes: slow and fast
        # Slow: use pyppeteer to query results by class_id, and take screenshot, send in channel
        # pros: looks pretty, easier to read
        # cons: I'm not sure how much I trust the ability to parse the class_id (see class_id assumption)
        # also, slower by like 7 seconds, might be annoying when browsing through lots of different classes

        # Fast: Just send 
        # pros:
        # cons: Looks pretty ugly, quite a bit harder to read easily (especially picking out the important)
        # bits like enrollment status and instructor

        if mode == "slow":
            browser = await launch()

            for i, name_soup_pair in enumerate(htmls):
                # class_no assumption: the class_id is always the first 9 digits of the id of the first div in the
                # GetCourseSummary html
                class_id = parse_class_id(str(name_soup_pair[1]))
                await self._generate_image(browser, class_id, ctx, letter_choice=chr(i + 65) if choices else None)

            await browser.close()

        else:  # we're in fast mode
            for i, name_soup_pair in enumerate(htmls):
                parsed_class = self._parse_class(name_soup_pair)

                if display_description:
                    r = requests.get(parsed_class["url"])
                    soup = BeautifulSoup(r.content, "lxml")
                    parsed_class['description'] = \
                        soup.find("p", class_="class_detail_title", text="Course Description").findNext('p').contents[0]

                await ctx.channel.send(embed=self._generate_embed(parsed_class, letter_choice=chr(i + 65) if choices else None))

        return htmls

    @commands.command(help="Search for a class in preparation to add to watch list")
    async def search_class(self, ctx, *, args):
        # PARSE ARGUMENTS

        user_id = ctx.message.author.id

        arg_list = args.split(' ')
        # if the last word is "fast" or "slow", that's the mode
        if arg_list[-1].lower() in ["fast", "slow"]:
            mode = arg_list[-1].lower()
            arg_list.pop()
        else: 
            # otherwise, default to fast if not specified
            mode = "fast"

        catalog = arg_list.pop()

        subject = ' '.join(arg_list)


        htmls = await self._generate_class_view(ctx, subject, catalog, mode, choices=True)

        if len(htmls) == 0:
            await ctx.send(f"Couldn't find that class.")
            return

        emoji_choices = [chr(A_EMOJI_INT + n) for n in range(len(htmls))]

        while True:
            status = await ctx.send(f"Choose the class you want keep an eye on.")
            for emoji_choice in emoji_choices:
                await status.add_reaction(emoji_choice)
            await status.add_reaction(NO_EMOJI)

            try:
                r, _ = await self.bot.wait_for("reaction_add", check=lambda reaction, user: user == ctx.author)
            except asyncio.TimeoutError:
                return
            else:
                if r.emoji == NO_EMOJI:
                    await status.edit(content="Aborted!", delete_after=TMPMSG_DEFAULT)
                    return
                if r.emoji in emoji_choices:
                    await status.edit(content=f"You've selected choice {r.emoji}")
                    # The index of our choice will correspond with how "far" out emoji
                    # choice was past number that corresponds with the A emoji
                    choice_index = ord(r.emoji) - A_EMOJI_INT
                    break

        if choice_index is not None:
            # based on the emoji index, choose the corresponding entry of the htmls
            name_soup_pair = htmls[choice_index]
            # read
            try:
                a_file = open(f"speedchat_bot/ucla_data/watchlist/{user_id}.json", "r")
                json_object = json.load(a_file)
                a_file.close()
            except (FileNotFoundError, json.JSONDecodeError):
                json_object = []

            class_id = parse_class_id(str(name_soup_pair[1]))


            # initialize user's list of watched classes if no entries yet
            # if user_id not in json_object["classes"]:
            #     json_object["classes"][user_id] = []


            # check for duplicates
            for my_class in json_object:
                if class_id == my_class["class_id"]:
                    await ctx.channel.send("You're already keeping track of that class!")
                    return

            # write class_id, *current* enrollment_status, and a name to the json
            json_object.append({
                "class_id": parse_class_id(str(name_soup_pair[1])),
                "enrollment_data": name_soup_pair[1].select_one("div[id$=-status_data]").text,
                "class_name": name_soup_pair[0],
                "term": self.term,
            })

            a_file = open(f"speedchat_bot/ucla_data/watchlist/{user_id}.json", "w")
            json.dump(json_object, a_file)
            a_file.close()

    @commands.command(help="Display info about a class, including description")
    async def display_class(self, ctx, subject: str, catalog: str, mode="fast"):
        await self._generate_class_view(ctx, subject, catalog, mode, display_description=True)

    @commands.command(help="Choose a class to remove from watchlist.")
    async def remove_class(self, ctx, mode="fast"):

        user_id = ctx.message.author.id

        json_object = await self.see_classes(ctx, mode, choices=True)

        if json_object is None:
            return

        emoji_choices = [chr(A_EMOJI_INT + n) for n in range(len(json_object))]

        while True:
            status = await ctx.send(f"Choose the class you want keep an eye on.")
            for emoji_choice in emoji_choices:
                await status.add_reaction(emoji_choice)
            await status.add_reaction(NO_EMOJI)

            try:
                r, _ = await self.bot.wait_for("reaction_add", check=lambda reaction, user: user == ctx.author)
            except asyncio.TimeoutError:
                return
            else:
                if r.emoji == NO_EMOJI:
                    await status.edit(content="Aborted!", delete_after=TMPMSG_DEFAULT)
                    return
                if r.emoji in emoji_choices:
                    await status.edit(content=f"You've selected choice {r.emoji}")
                    # The index of our choice will correspond with how "far" out emoji
                    # choice was past number that corresponds with the A emoji
                    choice_index = ord(r.emoji) - A_EMOJI_INT
                    break

        if choice_index is not None:
            # based on the emoji index, choose the corresponding entry of the htmls
            removed_class = json_object.pop(choice_index)

            if len(json_object) == 0:
                if os.path.exists(f"speedchat_bot/ucla_data/watchlist/{user_id}.json"):
                    os.remove(f"speedchat_bot/ucla_data/watchlist/{user_id}.json")
            else:
                a_file = open(f"speedchat_bot/ucla_data/watchlist/{user_id}.json", "w")
                json.dump(json_object, a_file)
                a_file.close()

            await ctx.send("You removed " + removed_class["class_name"])

    def check_class(self, name_model_pair):
        """Use the GetCourseSummary endpoint to, given a model, get soup for all the rest of the info about the class like class_id, instructor, enrollment data, etc.
        
        Returns list of tuples of the form (class name from class_names JSON, associated soup from that corresponding model from class_names JSON)
        """
        name = name_model_pair[0]
        model = name_model_pair[1]

        params = {'search_by': 'subject', 'model': model, 'FilterFlags': filter_flags, '_': '1571869764769'}

        final_url = _generate_url(self.GET_COURSE_SUMMARY_URL, params)
        # print(final_url)
        r = requests.get(final_url, headers=HEADERS)

        soup = BeautifulSoup(r.content, features="lxml")
        # print(soup)
        return [(name, html) for html in soup.select(".row-fluid.data_row.primary-row.class-info.class-not-checked")]
        # print(self._parse_class(soup))

    @commands.command(help="see classes you're keeping track of")
    async def see_classes(self, ctx, mode="fast", choices=False):

        user_id = ctx.message.author.id

        try:
            a_file = open(f"speedchat_bot/ucla_data/watchlist/{user_id}.json", "r")
            json_object = json.load(a_file)
            print(json_object[0])
            a_file.close()
        except (FileNotFoundError, json.JSONDecodeError, KeyError, IndexError):
            await ctx.channel.send(
                "Looks like you don't have any classes kept track of, or your data got malformed.\nIf the file is malformed, try clearing it with `~clear_classes`.")
            return None


        if mode == "fast":
            for n, my_class in enumerate(json_object):
                # get class from public url
                params = {'t': self.term, 'sBy': 'classidnumber', 'id': my_class['class_id']}
                final_url = _generate_url(self.PUBLIC_RESULTS_URL, params)
                soup = BeautifulSoup(requests.get(final_url, headers=HEADERS).content, "lxml")

                await ctx.channel.send(embed=self._generate_embed(self._parse_class(soup), letter_choice=chr(n+65) if choices else None))

        else:  # we're in the slow mode
            browser = await launch()
            for n, my_class in enumerate(json_object):
                self._generate_image(browser, my_class['class_id'], ctx, letter_choice=chr(n+65) if choices else None)
            await browser.close()

        return json_object


    # @commands.command()
    # async def DM(self, ctx, user: discord.User, *, message=None):
    #     message = message or "This Message is sent via DM"
    #     await user.send(message)

    @commands.command(help='Clear classes a user\'s "to watch" list')
    async def clear_classes(self, ctx):
        user_id = ctx.message.author.id

        if os.path.exists(f"speedchat_bot/ucla_data/watchlist/{user_id}.json"):
            os.remove(f"speedchat_bot/ucla_data/watchlist/{user_id}.json")

        await ctx.send("Classes cleared.")

    @tasks.loop(seconds=15.0)
    async def check_for_change(self, ctx):
        """
        Loop that when activated, every 15 seconds checks if a class's status has changed.
        If a class's status has changed,
        
        """

        # iterate through all the files in the watchlist directory
        for user_watchlist in os.listdir("speedchat_bot/ucla_data/watchlist"):
            try:
                a_file = open(f"speedchat_bot/ucla_data/watchlist/{user_watchlist}", "r")
                json_object = json.load(a_file)
                a_file.close()
            except (FileNotFoundError, json.JSONDecodeError):
                # The file is not there/unreadable, no point going on to check
                return

            user_id, _ = os.path.splitext(user_watchlist)

            need_change = False

            for my_class in json_object:
                params = {'t': self.term, 'sBy': 'classidnumber', 'id': my_class['class_id']}
                final_url = _generate_url(self.PUBLIC_RESULTS_URL, params)
                soup = BeautifulSoup(requests.get(final_url, headers=HEADERS).content, "lxml")
                enrollment_data = soup.select_one("div[id$=-status_data]").text

                await self.bot.get_user(int(user_id)).send(f'{my_class["class_name"]} changed from **{my_class["enrollment_data"]}** to **{enrollment_data}**')

                #  Current status  changed from   previously recorded status
                if enrollment_data      !=        my_class["enrollment_data"]:
                    await self.bot.get_user(int(user_id)).send(
                        f'{my_class["class_name"]} changed from **{my_class["enrollment_data"]}** to **{enrollment_data}**')

                    my_class['enrollment_data'] = enrollment_data
                    need_change = True

            if need_change:
                a_file = open(f"speedchat_bot/ucla_data/watchlist/{user_watchlist}", "w")
                json.dump(json_object, a_file)
                a_file.close()

        print(self.check_for_change.current_loop)

    @check_for_change.after_loop
    async def after_slow_count(self, ctx):
        await ctx.send("Stopped checking for classes")

    @commands.command(help="Start the count")
    async def start_the_count(self, ctx):
        self.check_for_change.start(ctx)
        await self.bot.change_presence(status=discord.Status.online, activity=discord.CustomActivity("Updating"))

    @commands.command(help="Stop the count")
    async def stop_the_count(self, ctx):
        self.check_for_change.stop(ctx)
        await self.bot.change_presence(status=discord.Status.do_not_disturb, activity=discord.CustomActivity("Not updating"))
