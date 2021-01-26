from logging import warning
from sys import executable
import discord
from discord.ext import tasks
import json
import urllib.parse as urlparse
from urllib.parse import urlencode
import requests
import re
from bs4 import BeautifulSoup
import os
import argparse
import shutil
import time

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
    return [i for i in arr if i] 


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

def parse_term(html):
    """
    Given html from GetCourseSummary endpoint, extract the term.
    """
    term_regex = 'term_cd=([\d]{2}[FWS]{1})&'
    match = re.search(term_regex, str(html))
    return match[1] if match else None


def validate_term(my_string):
    template = re.compile('[\d]{2}[FWS]{1}')  # i.e. 20F
    if template.match(my_string) is None:
        return False
    else:
        return True


# Commands for looking up UCLA classes
class UCLA(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Regexes (regexi?) to catch all the different cases for the enrollment statuses of a class
        # also contain named capture groups so it's easy to pick up capacity vs count
        self.status_regexes = {
            "tenative": re.compile('^Tentative'),
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

        self.status_colors = {
            "tenative"    : 0xff0000,
            "cancelled"   : 0xff0000,
            "closedByDept": 0xff0000,
            "classFull"   : 0xff0000,
            "classOpen"   : 0x00ff00,
            "waitlistOnly": 0x00ff00,
            "waitlistFull": 0xff0000,
        }

        # The main urls we'll be scraping from
        self.PUBLIC_RESULTS_URL     = "https://sa.ucla.edu/ro/Public/SOC/Results"
        self.GET_COURSE_SUMMARY_URL = "https://sa.ucla.edu/ro/Public/SOC/Results/GetCourseSummary"
        self.COURSE_TITLES_VIEW     = "https://sa.ucla.edu/ro/Public/SOC/Results/CourseTitlesView"
        self.COURSE_TITLES_PAGE     = "https://sa.ucla.edu/ro/Public/SOC/Results/CourseTitlesView"

        self.default_term = "21W"
        self.data_dir = "speedchat_bot/ucla_data/{term}"

        self.daily_reload.start()
        self.check_for_change.start()

        self.parser = argparse.ArgumentParser()
        self.parser.add_argument('class_name', metavar='name', type=str, nargs='+', help='whole class name, subject + catalog number')
        self.parser.add_argument('--mode', dest='mode', default="fast")
        self.parser.add_argument('--term', dest='term', default=None)
        self.parser.add_argument('--deep', action='store_true')

        self.simple_parser = argparse.ArgumentParser()
        self.simple_parser.add_argument('--mode', dest='mode', default="fast")

        self.EXEC_PATH = os.environ.get("GOOGLE_CHROME_SHIM", None)


    def _get_current_terms(self):
        url = "https://sa.ucla.edu/ro/Public/SOC/"
        soup = BeautifulSoup(requests.get(url).content, "lxml")
        all_terms =  map(lambda el: el.attrs['value'], soup.select("option.select_term"))
        return list(filter(lambda x: validate_term(x), all_terms))

        
    
    def _search_for_class_model(self, subject, catalog=None, term=None):
        """
        Finds the model for each class that matches subject+catalog, and also attaches the "human readable" class name.

        subject: String of the class's subject in CAPS format, i.e. (MATH or COM SCI)
        catalog: String of the class's number, i.e. 61 or 131AH or M120

        returns a generator of tuples (class's "human readable name", model) that match the given subject + catalog
        e.g. (Mathematics (MATH) 19 - COVID-19: Patterns and Predictions in Art, {\"Term\":\"21W\",\"SubjectAreaCode\":\"MATH...)
        
        """

        class_list = []

        search_term = term or self.default_term

        if not os.path.exists(self.data_dir.format(term=search_term) + "/class_names.json") and search_term in self.current_terms:
            self._reload_classes(term=search_term)

        if search_term in self.current_terms:
            # we have a json for it, find it in there
            with open(self.data_dir.format(term=search_term) + "/class_names.json") as fp:
                # TODO: Maybe separate subjects into their own json?
                data = json.load(fp)['class_names']
                classes_in_subject = data[subject]
                for my_class in classes_in_subject:
                    if catalog is None or my_class[0].split()[0] == str(catalog):
                        class_list.append((f"{subject} {my_class[0]}", my_class[1]))
            
        else:
            # we don't bother storing a json, use old method
            model = {"subj_area_cd":subject,"search_by":"subject","term_cd":search_term,"SubjectAreaName":"Computer Science (COM SCI)","CrsCatlgName":"Enter a Catalog Number or Class Title (Optional)","ActiveEnrollmentFlag":"n","HasData":"True"}
            pageNumber = 1
            while True:
                params = {'search_by': 'subject', 'model': model, "pageNumber":pageNumber, 'FilterFlags': filter_flags, '_': '1571869764769'}

                url = _generate_url(self.COURSE_TITLES_VIEW, params)

                r = requests.get(url, headers=HEADERS)
                soup = BeautifulSoup(r.content, "lxml")
                div_script_pairs = zip(soup.select("h3.head"), soup.select("script"))

                for div, script in div_script_pairs:
                    # I'll define the *human catalog number* as the one we're selecting here
                    # UCLA seems to store some really wack catalog numbers inside the script,
                    # i.e. COM SCI M152A -> 0152A M
                    # I probably could figure out a pattern but I can't know every possibility
                    # Plus, if someone doesn't get the human name right, I think that's on them
                    # BUT WHAT IF SPACE IN CATALOG NUMBER
                    class_name = div.select_one('a[id$="-title"]').text
                    if class_name.split("-", 1)[0][:-1] == catalog:
                        class_list.append(  (div.select_one('a[id$="-title"]').text,  re.search("({.*?})", script.decode_contents())[1]) )
                # when we get past all the result pages, we'll get nothing from requests.get
                if r.content == b'':
                    break

                pageNumber += 1

        return class_list



    def _generate_embed(self, parsed_class, letter_choice=None, watched=False):
        """Build a Discord Embed message based on a class dictionary, for sending in a fast mode"""
        title = '{choice} {class_name}{in_list}'.format(choice=f"(Choice {letter_choice})" if letter_choice else '',
                                               class_name=parsed_class["class_name"], in_list=" (in your watchlist)" if watched else '')

        embedVar = discord.Embed(title=title, description=f'[{parsed_class["section_name"]}]({parsed_class["url"]})',
                                 color=self.status_colors[parsed_class["enrollment_status"]])
        embedVar.add_field(name="Term", value=parsed_class["term"], inline=True)
        embedVar.add_field(name="Times", value=parsed_class["times"], inline=True)
        embedVar.add_field(name="Days", value=parsed_class["days"], inline=True)
        embedVar.add_field(name="Locations", value=parsed_class["locations"], inline=True)
        embedVar.add_field(name="Instructors", value=parsed_class["instructors"], inline=True)

        # this forces next fields onto new line
        embedVar.add_field(name = chr(173), value = chr(173))

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

    def _generate_all_embeds(self, htmls, display_description=False, choices=False, user_id=None):
        """Generate all the embed from a list of htmls, and return a list will all of them"""
        embed_list = []
        for i,name_soup_pair in enumerate(htmls):
            parsed_class = self._parse_class(name_soup_pair)

            # if we want to display class description, get it from the class details page
            if display_description:
                r = requests.get(parsed_class["url"])
                soup = BeautifulSoup(r.content, "lxml")
                parsed_class['description'] = \
                    soup.find("p", class_="class_detail_title", text="Course Description").findNext('p').contents[0]

            # generate and display embed with appropriate letter choice if desired
            generated_embed = self._generate_embed(parsed_class, letter_choice=chr(i + 65) if choices else None, watched=self._is_watching(user_id, parsed_class["class_id"]))
            embed_list.append(generated_embed)

        return embed_list
                

    async def _generate_image(self, browser, class_id, ctx, letter_choice=None):
        """Take a picture of a class id's details page, for sending in a slow mode"""

        if os.path.exists("candidate.png"):
            os.remove("candidate.png")

        params = {'t': self.default_term, 'sBy': 'classidnumber', 'id': class_id}
        final_url = _generate_url(self.PUBLIC_RESULTS_URL, params)

        page = await browser.newPage()

        await page.goto(final_url)

        await page.waitForSelector('#resultsTitle')
        element = await page.querySelector('#resultsTitle')

        if letter_choice:
            await page.evaluate(f'document.querySelector("a[id$=\'-title\']").prepend("(Choice {letter_choice}) ")')

        await element.screenshot(path='candidate.png')
        if letter_choice:
            message = await ctx.channel.send(f"Choice {letter_choice}", file=discord.File('candidate.png'))
        else:
            message = await ctx.channel.send(file=discord.File('candidate.png'))

        if os.path.exists("candidate.png"):
            os.remove("candidate.png")

        return message

    @commands.command(help="Change the default term for searching. It is written, only coolguy5530 can use this command.", brief="Only used by creator.")
    @is_owner()
    async def switch_term(self, ctx, new_term: str):
        # First, is this the right format?
        is_term = validate_term(new_term)
        if not is_term:
            ctx.channel.send(f"Sorry, {new_term} looks like a malformed term.")
            return

        if self.default_term and self.default_term is new_term:
            ctx.channel.send(f"You're already on {self.default_term}!")
            return

        # If we pass the checks, actually switch term, and initialize class list
        self.default_term = new_term
        self._reload_classes()

    # @commands.command(help="Search for a class in preparation to add to watch list")    
    # async def reload_classes(self, ctx, term=None):
    #     self._reload_classes(ctx, term)


    def get_subjects_for_term(self, term):
        print(f"getting subjects json for {term}")
        r = requests.get(f"https://sa.ucla.edu/ro/Public/SOC/Results?t={term}&sBy=subject&subj=MATH")
        template = re.compile("SearchPanelSetup\('(.*?)'")
        soup  = BeautifulSoup(r.content, "lxml")
        for script in soup.select("script"):
            matches = template.search(str(script))
            if matches:
                subjects = json.loads(matches[1].replace("&quot;", '"'))
                if term and not os.path.exists(self.data_dir.format(term=term)):
                    os.mkdir(self.data_dir.format(term=term))

                subjects_file = open(self.data_dir.format(term=term or self.default_term) + "/subjects.json", "w+")
                subjects_file.write(json.dumps(subjects))
                subjects_file.close()
                return

    def _reload_classes(self, term=None):
        # Load list of subjects parsed from UCLA website
        self.get_subjects_for_term(term or self.default_term)

        f = open(self.data_dir.format(term=(term or self.default_term)) + "/subjects.json")
        self.subjectsJSON = json.load(f)
        f.close()

        class_name_dict = {}

        # we're sending command from discord channel, so force the reload goes through regardless of when last updated

        print(f"Reloading the {term or self.default_term} class names JSON (this may take a minute or 2)...")
        for n, subject in enumerate(self.subjectsJSON):
            pageNumber = 1

            # Replace everything but spaces, which get changed to "+", i.e. "ART HIS" -> "ART+HIS"
            model = {"subj_area_cd":subject["value"],"search_by":"subject","term_cd":term or self.default_term,"SubjectAreaName":"Computer Science (COM SCI)","CrsCatlgName":"Enter a Catalog Number or Class Title (Optional)","ActiveEnrollmentFlag":"n","HasData":"True"}
            all_classes = []
            while True:
                params = {'search_by': 'subject', 'model': model, "pageNumber":pageNumber, 'FilterFlags': filter_flags, '_': '1571869764769'}

                url = _generate_url(self.COURSE_TITLES_VIEW, params)

                r = requests.get(url, headers=HEADERS)
                soup = BeautifulSoup(r.content, "lxml")
                div_script_pairs = zip(soup.select("h3.head"), soup.select("script"))

                for div, script in div_script_pairs:
                    # I can't guarantee that there isn't some wack scenario where there are two classes
                    # names exactly the same, make each name+model pair like a tuple instead
                    all_classes.append(
                        [div.select_one('a[id$="-title"]').text, re.search("Iwe_ClassSearch_SearchResults.AddToCourseData\(.*?({.*?})", script.decode_contents())[1]])
                # when we get past all the result pages, we'll get nothing from requests.get
                if r.content == b'':
                    break

                pageNumber += 1

            class_name_dict[subject["value"].strip()] = all_classes

        print("Done reloading")

        class_names_file = open(self.data_dir.format(term=term or self.default_term) + "/class_names.json", "w")
        class_names_file.write(
            json.dumps({"last_updated": time.time(), "term": term or self.default_term, "class_names": class_name_dict}, sort_keys=True))
        class_names_file.close()

    def _parse_enrollment_status(self, my_string):
        """
        Go through the dictionary of enrollment regexes, return an enrollment dictionary
        with count, capacity, etc numbers when the right match is found.
        """

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
        """
        Go through the dictionary of waitlist regexes, return a waitlist dictionary when
        the right match is found.
        """
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

    def _parse_class(self, name_soup_pair):
        if type(name_soup_pair) is tuple:
            name = name_soup_pair[0]
            soup = name_soup_pair[1]
        else:  # we sent to this function soup from the public records page, which has name info on it
            name = name_soup_pair.select_one("a[id$=-title]").text
            soup = name_soup_pair
        enrollment_data = soup.select_one("div[id$=-status_data]").text
        waitlist_data = soup.select_one("div[id$=-waitlist_data]").text.replace("\n", '')

        locations = _parse_string_to_array(soup.select_one("div[id$=-location_data]")) or ["N/A"]
        days = _parse_string_to_array(soup.select_one("div[id$=-days_data] p a")) or ["N/A"]
        times = _parse_string_to_array(soup.select_one("div[id$=-time_data]>p")) or ["N/A"]

        instructors = _parse_string_to_array(soup.select_one("div[id$=-instructor_data]>p") or None)

        # I hope it always looks lile <div id="blah-units_data"><p> # of units </p></div>
        # could be wrong...
        units = soup.select_one("div[id$=-units_data] p").text

        details_url = "https://sa.ucla.edu" + soup.select_one('a[title^="Class Detail for "]')['href']
        section_name = soup.select_one('a[title^="Class Detail for "]').text
        details_url_parts = dict(urlparse.parse_qsl(list(urlparse.urlparse(details_url))[4]))

        class_dict = {
            "subject":         details_url_parts['subj_area_cd'].strip(),
            "class_no":        details_url_parts['class_no'].strip(),
            "class_id":        parse_class_id(str(soup)),
            "class_name":      name,
            "term":            parse_term(str(soup)),
            "section_name":    section_name,
            "instructors":     '\n'.join(instructors),
            "days":            '\n'.join(days),
            "times":           '\n'.join(times),
            "locations":       '\n'.join(locations),
            "units":           units,
            "url":             details_url,
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

    def _get_user_watchlist(self, user_id):
        try:
            a_file = open(f"speedchat_bot/ucla_data/watchlist/{user_id}.json", "r")
            json_object = json.load(a_file)
            a_file.close()
        except (FileNotFoundError, json.JSONDecodeError):
            json_object = None

        return json_object


    def _is_watching(self, user_id, class_id):
        """Checks if a user is tracking a certain class's id"""

        if user_id is None:
            return False

        watchlist = self._get_user_watchlist(user_id)

        if watchlist is None:
            return False

        for my_class in watchlist:
            if my_class["class_id"] == class_id:
                return True

        return False


    @commands.command(brief="Displays the default term", help="Displays the default term. This is the term that all commands default to when you don't provide a term argument.")
    async def default_term(self, ctx):
        await ctx.send(f"The default term is {self.default_term}")
        

    async def _generate_class_view(self, ctx, subject: str, catalog=None, term=None, user_id=None, mode="slow", display_description=False, choices=False):
        """
        Given the lookup info of subject+catalog (i.e. MATH+151AH), send either embeds or images based
        on the resulting soups (from GetCourseSummary). Returns that a list that pairs the html with its associated message.
        """
        await ctx.send(f"Searching for\nSubject: {subject}\nCatalog: {catalog or 'N/A'}\nTerm: {term or self.default_term}\nUser: {ctx.message.author.name}\n")
        user_id = ctx.message.author.id


        model_choices = self._search_for_class_model(subject, catalog, term)

        htmls = []
        for name_model_pair in model_choices:
            print(name_model_pair[1])
            htmls = htmls + self.check_class(name_model_pair)


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

        messages = []
        if mode == "slow":
            browser = await launch(headless=True, executablePath=self.EXEC_PATH, args=['--no-sandbox'])

            for i, name_soup_pair in enumerate(htmls):
                # class_no assumption: the class_id is always the first 9 digits of the id of the first div in the
                # GetCourseSummary html
                class_id = parse_class_id(str(name_soup_pair[1]))
                message = await self._generate_image(browser, class_id, ctx, letter_choice=chr(i + 65) if choices else None)
                messages.append(message)

            await browser.close()

        else:  # we're in fast mode
            embed_list = self._generate_all_embeds(htmls, display_description=display_description, user_id=user_id, choices=choices)
            for generated_embed in embed_list:
                message = await ctx.channel.send(embed=generated_embed)
                messages.append(message)

        if len(htmls) == 0:
            await ctx.channel.send("Sorry, I couldn't find that class.")
        return list(zip(htmls, messages))

    async def _present_choices(self, ctx, num_choices):
        """Given a (int) number of choices, send a message asking to choose one, with reactions for easy selecting"""
        emoji_choices = [chr(A_EMOJI_INT + n) for n in range(num_choices)]
        status = await ctx.send(f"Choose the class you want keep an eye on/remove from your watchlist.")
        while True:
            
            for emoji_choice in emoji_choices:
                await status.add_reaction(emoji_choice)
            await status.add_reaction(NO_EMOJI)

            try:
                r, _ = await self.bot.wait_for("reaction_add", check=lambda reaction, user: user == ctx.author)
            except asyncio.TimeoutError:
                return
            else:
                # check if this is the right user, and the right message
                reactors  = await r.users().flatten()
                if r.message.id == status.id and ctx.author in reactors:
                    if r.emoji == NO_EMOJI:
                        await status.edit(content="Aborted!", delete_after=TMPMSG_DEFAULT)
                        return None
                    if r.emoji in emoji_choices:
                        await status.edit(content=f"You've selected choice {r.emoji}")
                        # The index of our choice will correspond with how "far" out emoji
                        # choice was past number that corresponds with the A emoji
                        choice_index = ord(r.emoji) - A_EMOJI_INT

                        if ctx.guild:
                            for emoji_choice in emoji_choices:
                                await status.clear_reaction(emoji_choice)
                            await status.clear_reaction(NO_EMOJI)

                        return choice_index



    @commands.command(brief="Search for a class in preparation to add to watch list.", help="Usage: ~search_class subject number [--mode] [--term]\n\nsubject: The subject area of the class you're looking for. Must be in the format that the Class Planner displays, i.e. COM SCI, or C&S BIO.\nnumber: The class number, i.e. 151A or M120 or A. No spaces.\nterm: Which term to search for the class in. Must be formatted like 20F/21W/21S.\nmode: Optional parameter, must be 'fast' or 'slow'.\n\nFast mode: displays embeds for each class in the watchlist.\nSlow mode: displays images from the class details webpage for each class in the watchlist.\n\nSearch for a class in preparation to add to watch list.\n\nPresents all classes that match the class you queried, and present emoji reaction choices. Reacting with a certain emoji will add the corresponding class to your watchlist.")
    @first_time()
    async def search_class(self, ctx, *, args):
        # PARSE ARGUMENTS
        user_id = ctx.message.author.id

        args = vars(self.parser.parse_args(args.split()))

        catalog = args["class_name"].pop().upper()

        subject = ' '.join(args["class_name"]).upper()


        if args.get("term") and not validate_term(args["term"]):
            await ctx.send(f"{args['term']} looks like a malformed term. Needs to be of the form 20F/21W/21S")
            return

        if args.get("mode") and args["mode"] not in ["fast", "slow"]:
            await ctx.send(f"The mode must be fast or slow, I saw {args['mode']}")
            return

        if not os.path.exists(self.data_dir.format(term=args.get("term") or self.default_term) + "/class_names.json"):
            await ctx.send(f"You haven't looked up classes from {args.get('term') or self.default_term} before, this might take a minute or 2 to load all the classes")

        # fetch list of class HTMLS
        try:
            messages = await self._generate_class_view(ctx, subject, catalog, args["term"], user_id, args["mode"], choices=True)
        except KeyError:
            await ctx.send(f"Sorry, I don't think {subject} is a real subject.\nNote that you must use the subject abbreviation you see on the Class Planner, i.e. MATH or COM SCI or C&S BIO")
            raise KeyError(f"Couldn't find subject {subject}")
        
        # check if we actually found any
        if len(messages) == 0:
            return

        # Ask the user which one they want to select
        choice_index = await self._present_choices(ctx, len(messages))

        # Warning if term is really long ago
        if args.get("term") not in self.current_terms:
            await ctx.send(f"{args.get('term')} doesn't seem to be relevant right now. Are you sure you want to track a class from that term?")
        # And add that selection to their watchlist
        if choice_index is not None:
            name_soup_pair, _ = messages.pop(choice_index)

            for _, message in messages:
                await message.delete()

            # read

            json_object = self._get_user_watchlist(user_id) or []

            parsed_class = self._parse_class(name_soup_pair)

            # check for duplicates
            for my_class in json_object:
                if parsed_class['class_id'] == my_class["class_id"] and parsed_class['term'] == my_class["term"]:
                    await ctx.channel.send("You're already keeping track of that class!")
                    return

            # write class_id, *current* enrollment_status, and a name to the json
            json_object.append({
                "class_id": parsed_class['class_id'],
                "enrollment_data": name_soup_pair[1].select_one("div[id$=-status_data]").text,
                "class_name": name_soup_pair[0],
                "term": parsed_class["term"],
            })

            a_file = open(f"speedchat_bot/ucla_data/watchlist/{user_id}.json", "w")
            json.dump(json_object, a_file)
            a_file.close()

    @commands.command(
        help="Display all classes under a given subject.\n Fast mode",
        brief="Display all classes under a given subject."
        )
    @first_time()
    async def subject(self, ctx, *, args):
        # PARSE ARGUMENTS
        user_id = ctx.message.author.id

        args = vars(self.parser.parse_args(args.split()))

        subject = ' '.join(args["class_name"]).upper()

        
        if args.get("term") and not validate_term(args["term"]):
            await ctx.send(f"{args['term']} looks like a malformed term. Needs to be of the form 20F/21W/21S")
            return

        if args.get("mode") and args["mode"] not in ["fast", "slow"]:
            await ctx.send(f"The mode must be fast or slow, I saw {args['mode']}")
            return

        if not os.path.exists(self.data_dir.format(term=args.get("term") or self.default_term) + "/class_names.json"):
            await ctx.send(f"You haven't looked up classes from {args.get('term') or self.default_term} before, this might take a minute or 2 to load all the classes")

        # fetch list of class HTMLS
        all_classes = []
        if args.get("deep"):
            page_length = 5
            try:
                warning_message = await ctx.send(f"You're looking up all the classes in a {subject}, this might take a second to load...")
                class_models = self._search_for_class_model(subject, catalog=None, term=args.get("term"))
                htmls = []
                for name_model_pair in class_models:
                    print(name_model_pair[1])
                    htmls = htmls + self.check_class(name_model_pair)

                all_classes = self._generate_all_embeds(htmls, user_id=user_id)
                await warning_message.delete()
            except KeyError:
                await ctx.send(f"Sorry, I don't think {subject} is a real subject.\nNote that you must use the subject abbreviation you see on the Class Planner, i.e. MATH or COM SCI or C&S BIO")
                raise KeyError(f"Couldn't find subject {subject}")
            

        else:
            page_length = 10
            term_to_search = args.get('term') or self.default_term
            if term_to_search in self.current_terms:
                f = open(self.data_dir.format(term=term_to_search) + "/class_names.json")
                json_object = json.load(f)['class_names']
                f.close()
                if subject in json_object:
                    all_classes = [my_class[0] for my_class in json_object[subject]]
            else:
                await ctx.send(f"Sorry, {args.get('term')} happened too long ago, and the classes there not stored in this bot's database.")
                return

        found = len(all_classes)
        # check if we actually found any
        if found == 0:
            return

        status = await ctx.send(f"Gathering classes")
        idx = 0
        messages = []
        htmls = []
        while True:

            await status.edit(content=f"Here's entries {idx} through {idx+page_length}:")
            
            preview = all_classes[idx:idx+page_length]
            if type(all_classes[0]) == str:
                messages.append(await ctx.send('\n'.join(preview)))
            else:
                for generated_embed in preview:
                    messages.append(await ctx.send(embed=generated_embed))

            display_more = await ctx.send("Display more?")


            await display_more.add_reaction("⬅️")
            await display_more.add_reaction("➡️")
            try:
                r, _ = await self.bot.wait_for("reaction_add", check=lambda r, u: u == ctx.author and r.message.id == display_more.id)
            except asyncio.TimeoutError:
                break
            else:
                if r.emoji == "⬅️":
                    idx -= page_length
                if r.emoji == "➡️":
                    idx += page_length
                if idx >= found or idx <= 0:
                    idx = 0

                # clear reactions and previous message
                for message in messages:
                    await message.delete()

                messages = []
                await display_more.delete()






    @commands.command(brief="Display info about a class, including description", help="Usage: ~display_class subject number [--mode] [--term]\n\nsubject: The subject area of the class you're looking for. Must be in the format that the Class Planner displays, i.e. COM SCI, or C&S BIO.\nnumber: The class number, i.e. 151A or M120 or A. No spaces.\nterm: Which term to search for the class in. Must be formatted like 20F/21W/21S.\nmode: Optional parameter, must be 'fast' or 'slow'.\n\nFast mode: displays embeds for each class in the watchlist.\nSlow mode: displays images from the class details webpage for each class in the watchlist.\n\nDisplay info about a class, including description.\n\nSame as ~search_class, but displays course description and not providing option to add to watchlist.")
    @first_time()
    async def display_class(self, ctx, *, args):
        user_id = ctx.message.author.id

        args = vars(self.parser.parse_args(args.split()))
        catalog = args["class_name"].pop().upper()
        subject = ' '.join(args["class_name"]).upper()


        htmls = await self._generate_class_view(ctx, subject, catalog, args.get("term"), user_id, args["mode"], display_description=True)

    @commands.command(brief="Choose a class to remove from watchlist.", help="Usage: ~remove_class [--mode]\n\\n\nmust be 'fast' or 'slow'. \nFast mode: displays embeds for each class in the watchlist.\nSlow mode: displays images from the class details webpage for each class in the watchlist.\n\nnChoose a class to remove from watchlist. Calling this command will present each class with choice reaction emojis; choose the emoji corresponding with a certain class to remove it from your watchlist, and stop getting notifications from it.")
    async def remove_class(self, ctx, *, args):

        user_id = ctx.message.author.id
        args = vars(self.simple_parser.parse_args(args.split()))   
        json_object, messages = await self.see_watchlist(ctx, mode=args.get("mode"), choices=True)

        if json_object is None:
            return

        choice_index = await self._present_choices(ctx, len(json_object))

        if choice_index is not None:
            # based on the emoji index, choose the corresponding entry of the htmls
            removed_class = json_object.pop(choice_index)
            message = messages.pop(choice_index)
            await message.delete()

            if len(json_object) == 0:
                if os.path.exists(f"speedchat_bot/ucla_data/watchlist/{user_id}.json"):
                    os.remove(f"speedchat_bot/ucla_data/watchlist/{user_id}.json")
            else:
                a_file = open(f"speedchat_bot/ucla_data/watchlist/{user_id}.json", "w")
                json.dump(json_object, a_file)
                a_file.close()

            await ctx.send("You removed " + removed_class["class_name"])

    def check_class(self, name_model_pair):
        """
        Use the GetCourseSummary endpoint to, given a model, get soup for all the rest of the info about the class like class_id, instructor, enrollment data, etc.

        Returns list of tuples of the form (class name from class_names JSON, associated soup from that corresponding model from class_names JSON)
        """
        name = name_model_pair[0]
        model = name_model_pair[1]

        params = {'search_by': 'subject', 'model': model, 'FilterFlags': filter_flags, '_': '1571869764769'}

        final_url = _generate_url(self.GET_COURSE_SUMMARY_URL, params)
        r = requests.get(final_url, headers=HEADERS)

        soup = BeautifulSoup(r.content, features="lxml")
        return [(name, html) for html in soup.select(".row-fluid.data_row.primary-row.class-info.class-not-checked")]
        # print(self._parse_class(soup))

    @commands.command(brief="See classes you're keeping track of.", help="Usage: ~see_watchlist [--mode]\nmode: must be 'fast' or 'slow'. \nFast mode: displays embeds for each class in the watchlist.\nSlow mode: displays images from the class details webpage for each class in the watchlist.\n\nSee classes you're keeping track of.")
    @first_time()
    async def see_watchlist(self, ctx, *, args, choices=False):

        user_id = ctx.message.author.id
        args = vars(self.simple_parser.parse_args(args.split()))
        json_object = self._get_user_watchlist(user_id)

        if json_object is None or len(json_object) == 0:
            await ctx.channel.send(
                "Looks like you don't have any classes kept track of, or your data got malformed.\nIf the file is malformed, try clearing it with `~clear_classes`.")
            return None, None

        messages = []

        if args.get("mode") == "fast":
            for n, my_class in enumerate(json_object):
                # get class from public url
                params = {'t': my_class["term"], 'sBy': 'classidnumber', 'id': my_class['class_id']}
                final_url = _generate_url(self.PUBLIC_RESULTS_URL, params)
                soup = BeautifulSoup(requests.get(final_url, headers=HEADERS).content, "lxml")

                message = await ctx.channel.send(embed=self._generate_embed(self._parse_class(soup), letter_choice=chr(n+65) if choices else None, watched=self._is_watching(user_id, my_class['class_id'])))
                messages.append(message)

        else:  # we're in the slow mode
            browser = await launch(headless=True, executablePath=self.EXEC_PATH, args=['--no-sandbox'])
            for n, my_class in enumerate(json_object):
                message = await self._generate_image(browser, my_class['class_id'], ctx, letter_choice=chr(n+65) if choices else None)
                messages.append(message)
            await browser.close()
        
        await ctx.send(f"There are the classes in {ctx.message.author.name}'s watchlist.")

        return json_object, messages


    @commands.command(brief='Clear classes a user\'s "to watch" list', help='Clears classes from a user\'s "to watch" list, if you have added classes to it. This means you\'ll stop recieving notifications.')
    async def clear_classes(self, ctx):
        user_id = ctx.message.author.id

        if self._get_user_watchlist(user_id):
            os.remove(f"speedchat_bot/ucla_data/watchlist/{user_id}.json")

        await ctx.send(f"Classes cleared for {ctx.message.author.name}.")

    @tasks.loop(seconds=15.0)
    async def check_for_change(self):
        """
        Loop that when activated, every 15 seconds checks if a class's status has changed.
        If a class's status has changed, alert user that was watching it, and update their watchlist's data
        
        """

        # iterate through all the files in the watchlist directory
        for user_watchlist in os.listdir("speedchat_bot/ucla_data/watchlist"):

            user_id, _ = os.path.splitext(user_watchlist)
            json_object = self._get_user_watchlist(user_id)

            if json_object is None:
                # The file is not there/unreadable, no point going on to check
                break

            need_change = False

            for my_class in json_object:
                params = {'t': my_class['term'], 'sBy': 'classidnumber', 'id': my_class['class_id']}
                final_url = _generate_url(self.PUBLIC_RESULTS_URL, params)
                soup = BeautifulSoup(requests.get(final_url, headers=HEADERS).content, "lxml")
                enrollment_data = soup.select_one("div[id$=-status_data]").text

                # await self.bot.get_user(int(user_id)).send(f'{my_class["class_name"]} changed from **{my_class["enrollment_data"]}** to **{enrollment_data}**')

                #  Current status  changed from   previously recorded status
                if enrollment_data      !=        my_class["enrollment_data"]:
                    myid = f"<@{user_id}>"
                    await self.bot.get_user(int(user_id)).send(
                        f'{myid} {my_class["class_name"]} changed from **{my_class["enrollment_data"]}** to **{enrollment_data}**')

                    my_class['enrollment_data'] = enrollment_data
                    need_change = True

            if need_change:
                # update watchlist
                a_file = open(f"speedchat_bot/ucla_data/watchlist/{user_watchlist}", "w")
                json.dump(json_object, a_file)
                a_file.close()

        print(self.check_for_change.current_loop)

    

    @check_for_change.after_loop
    async def after_slow_count(self, ctx):
        await ctx.send("Stopped checking for classes")


    @commands.command(brief="Only used by creator.", help="Stop checking for changes in users' watchlists. It is written, only coolguy5530 can use this command.")
    @is_owner()
    async def stop_the_count(self, ctx):
        self.check_for_change.stop()
        await self.bot.change_presence(status=discord.Status.do_not_disturb, activity=discord.Game("Not updating"))


    def _needs_reload(self, term):
        if not os.path.exists(self.data_dir.format(term=term or self.default_term) + "/class_names.json"):
            return True
        else:
            f = open(self.data_dir.format(term=term or self.default_term) + "/class_names.json")
            json_object = json.load(f)
            f.close()

            # if the last time the json was updated was less than a week ago, we don't have to actually reload
            if (time.time() - json_object["last_updated"]) < 7 * 24 * 3600:
                return False
            else:
                return True


    @tasks.loop(hours=24)
    async def daily_reload(self):
        print("Starting daily reload")
        # flush data
        self.current_terms = self._get_current_terms()

        data_dirs = list(os.walk("speedchat_bot/ucla_data"))[0][1]
        if "watchlist" in data_dirs:
            data_dirs.remove("watchlist")
        for term_folder in data_dirs:
            if term_folder not in self.current_terms:
                shutil.rmtree("speedchat_bot/ucla_data/"+term_folder)

        for term in self.current_terms:
            if self._needs_reload(term):
                print(f"{term} needs a reload")
                self._reload_classes(term=term)
                break # reload at most 1 class