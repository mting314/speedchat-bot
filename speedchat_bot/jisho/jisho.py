import requests
from itertools import zip_longest
from bs4 import BeautifulSoup
from .kana import hiragana, katakana, small_characters, hira2eng, kata2eng
import re
import urllib
import html
import json

ONYOMI_LOCATOR_SYMBOL = 'On'
KUNYOMI_LOCATOR_SYMBOL = 'Kun'

JISHO_API = 'https://jisho.org/api/v1/search/words'
SCRAPE_BASE_URI = 'jisho.org/search/'
STROKE_ORDER_DIAGRAM_BASE_URI = 'https://classic.jisho.org/static/images/stroke_diagrams/'


def remove_new_lines(my_string):
    return re.sub('/(?:\r|\n)/g', '', my_string).strip()

def uriForSearch(kanji, filter = "words"):
    return "https://" + urllib.parse.quote(f'{SCRAPE_BASE_URI}{kanji}#{filter}')

# def uriForKanjiSearch(kanji):
#     return "https://" + urllib.parse.quote(f'{SCRAPE_BASE_URI}{kanji}#kanji')

# I'm 99% sure this is bugged/doesn't work anymore because classic.jisho.org doesn't seem to exist anymore
def getUriForStrokeOrderDiagram(kanji):
    return STROKE_ORDER_DIAGRAM_BASE_URI + kanji.encode("unicode-escape").decode("utf-8").replace("\\u", '') + '_frames.png'

def uriForPhraseSearch(phrase):
    return f'{JISHO_API}?keyword={urllib.parse.quote(phrase)}'

def get_string_between_strings(data, start_string, end_string):
    regex = f'{re.escape(start_string)}(.*?){re.escape(end_string)}'
    # Need DOTALL because the HTML still has its newline characters
    match = re.search(regex, str(data), re.DOTALL)

    return match[1] if match is not None else None


def parseAnchorsToArray(my_string):
    regex = r'<a href=".*?">(.*?)</a>'
    return re.findall(regex, my_string)


def getGifUri(kanji):
    fileName = kanji.encode("unicode-escape").decode("utf-8").replace("\\u", '') + '.gif'
    animationUri = f'https://raw.githubusercontent.com/mistval/kanji_images/master/gifs/{fileName}'
    return animationUri


def kana_to_halpern(untrans):
    """Take a word completely in hiragana or katakana and translate it into romaji"""
    halpern = []
    while untrans:

        if len(untrans) > 1:
            first = untrans[0]
            second = untrans[1]
        else:
            first = untrans[0]
            second = None

        if first in hiragana:
            if second and second in ["ゃ", "ゅ", "ょ"]:
                halpern.append(hira2eng[first + second])
                untrans = untrans[2:]
            else:
                halpern.append(hira2eng[first])
                untrans = untrans[1:]
        else:
            if second and second in ["ャ", "ュ", "ョ"]:
                halpern.append(kata2eng[first + second])
                untrans = untrans[2:]
            else:
                halpern.append(kata2eng[first])
                untrans = untrans[1:]

        del first
        del second

    return "".join(halpern)



def _get_full_vocabulary_string(html):
    """Return the full furigana of a word from the html."""
    # The kana represntation of the Jisho entry is contained in this div
    text_markup = html.find(class_="concept_light-representation")

    upper_furigana = text_markup.find(class_="furigana").find_all('span')
    inset_furigana = text_markup.find(class_="text").children

    # inset_furigana needs more formatting due to potential bits of kanji sticking together
    inset_furigana_list = []
    for f in inset_furigana:
        cleaned_text = f.string.replace("\n", "").replace(" ", "")
        if cleaned_text == "":
            continue
        elif len(cleaned_text) > 1:
            for s in cleaned_text:
                inset_furigana_list.append(s)
        else:
            inset_furigana_list.append(cleaned_text)

    children = zip_longest(upper_furigana, inset_furigana_list)

    full_word = []
    for c in children:
        if c[0].text != '':
            full_word.append(c[0].text)
        elif c[0].text == '' and contains_kana(c[1]):
            full_word.append(c[1])
        else:
            continue

    # print(''.join(full_word))
    # print("====")
    return ''.join(full_word)

def contains_kana(word):
    """Takes a word and returns true if there are hiragana or katakana present within the word"""
    for k in word:
        if k in hiragana or k in katakana or k in small_characters:
            return True
    return False

kanjiRegex = '[\u4e00-\u9faf\u3400-\u4dbf]'


def getKanjiAndKana(div):
    ul = div.select_one('ul')
    # contents = ul.contents()

    kanji = ''
    kana = ''
    for child in ul.children:
        if child.name == 'li':
            li = child
            furigana = li.select_one("span.furigana").text if li.select_one("span.furigana") is not None else None
            unlifted = li.select_one("span.unlinked").text if li.select_one("span.unlinked") is not None else None

            if furigana:
                kanji += unlifted
                kana += furigana

                kanaEnding = []
                for i in reversed(range(len(unlifted))):
                    if not re.search(kanjiRegex, unlifted[i]):
                        kanaEnding.append(unlifted[i])
                    else:
                        break

                kana += ''.join(kanaEnding[::-1])
            else:
                kanji += unlifted
                kana += unlifted
        else:
            text = str(child).strip()
            if text:
                kanji += text
                kana += text

    return kanji, kana


def getPieces(sentenceElement):
    pieceElements = sentenceElement.select("li.clearfix") + sentenceElement.select("el")
    pieces = []

    for pieceElement in pieceElements:
        if pieceElement.name == 'li':
            pieces.append({
                'lifted': pieceElement.select_one("span.furigana").text if pieceElement.select_one("span.furigana") is not None else '',
                'unlifted': pieceElement.select_one("span.unlinked").text if pieceElement.select_one("span.unlinked") is not None else '',
            })
        else:
            pieces.append({
                'lifted': '',
                'unlifted': pieceElement.text,
            })

    return pieces


def parseExampleDiv(div):
    english = str(div.select_one('span.english').find(text=True))
    kanji, kana = getKanjiAndKana(div)

    return english, kanji, kana, getPieces(div)


def parse_example_page_data(pageHtml, phrase):
    string_page_html = str(pageHtml)
    # pageHtmlReplaced = re.sub(
        # r'</li>\s*([^\s<>]+)\s*<li class="clearfix">', r'</li><el>\1</el><li class="clearfix">', string_page_html)
    # myhtml = BeautifulSoup(pageHtmlReplaced, 'lxml')
    divs = pageHtml.select("div.sentence_content")

    results = []
    for div in divs:
        # div = divs.eq(i)
        results.append(parseExampleDiv(div))

    return {
        'query': phrase,
        'found': len(results) > 0,
        'result': results,
        'uri': uriForSearch(phrase, filter="sentences"),
        'phrase': phrase
    }


# PHRASE SCRAPE FUNCTIONS START

def get_tags(my_html):
    tags = []

    tagElements = my_html.select("span.concept_light-tag")
    for tagElement in tagElements:
        tags.append(tagElement.text)

    return tags


def getMeaningsOtherFormsAndNotes(my_html):
    otherForms = []
    notes = []

    meaningsWrapper = my_html.select_one(
        '#page_container > div > div > article > div > div.concept_light-meanings.medium-9.columns > div')
    meaningsChildren = meaningsWrapper.children
    meanings = []

    mostRecentWordTypes = []
    for child in meaningsChildren:
        if child.get("class")[0] == 'meaning-tags':
            mostRecentWordTypes = list(map(lambda x: x.strip().lower(), child.text.split(',')))
        elif mostRecentWordTypes[0] == 'other forms':
            otherForms = list(map(lambda y: ({'kanji': y[0], 'kana': y[1]}),
                                  map(lambda x: x.replace('【', '').replace('】', '').split(' '),
                                      child.text.split('、'))))
        elif mostRecentWordTypes[0] == 'notes':
            notes = child.text().split('\n')
        else:
            meaning = child.select_one("span.meaning-meaning").text
            try:
                child.select_one('.meaning-abstract').select_one('a').extract().end()
                meaningAbstract = child.select_one('.meaning-abstract').text
            except AttributeError:
                meaningAbstract = ''

            try:
                supplemental = list(filter(lambda y: bool(y),
                                    map(lambda x: x.strip(), child.select_one("span.supplemental_info").text.split(','))))
            except AttributeError: # if we couldn't find supplemental info class
                supplemental = []

            seeAlsoTerms = []
            for i in reversed(range(len(supplemental))):
                supplementalEntry = supplemental[i]
                if supplementalEntry.startswith('See also'):
                    seeAlsoTerms.append(supplementalEntry.replace('See also ', ''))
                    supplemental.pop(i)

            sentences = []
            sentenceElements = child.select_one("span.sentences > div.sentence") or []

            for sentenceElement in sentenceElements:

                english = sentenceElement.select_one("li.english").text
                pieces = getPieces(sentenceElement)

                # remove english and furigana to get left with normal japanese
                sentenceElement.select_one("li.english").extract()
                # could (will) be multiple furiganas
                for s in sentenceElement.select("span.furigana"):
                    s.extract()

                japanese = sentenceElement.text

                sentences.append({'english': english, 'japanese': japanese, 'pieces': pieces})

            meanings.append({
                'seeAlsoTerms': seeAlsoTerms,
                'sentences': sentences,
                'definition': meaning,
                'supplemental': supplemental,
                'definitionAbstract': meaningAbstract,
                'tags': mostRecentWordTypes,
            })

    return meanings, otherForms, notes


def uri_for_phrase_scrape(searchTerm):
    return f'https://jisho.org/word/{urllib.parse.quote(searchTerm)}'


def parsePhrasePageData(pageHtml, query):
    my_html = BeautifulSoup(pageHtml, "lxml")
    meanings, otherForms, notes = getMeaningsOtherFormsAndNotes(my_html)

    result = {
        'found': True,
        'query': query,
        'uri': uri_for_phrase_scrape(query),
        'tags': get_tags(my_html),
        'meanings': meanings,
        'other_forms': otherForms,
        'notes': notes
    }

    return result




class Jisho:
    """
    A class to interface with Jisho.org and store search results for use.
    Stores html results from queries to Jisho.org as an instance variable
    and 

    """

    def __init__(self):
        self.html = None
        self.response = None

    def searchForPhrase(self, phrase):
        """Directly use Jisho's official API to get info on a phrase (can be multiple characters)"""
        uri = uriForPhraseSearch(phrase)
        return json.loads(requests.get(uri).content)

    def searchForKanji(self, kanji, depth = "shallow"):
        """Return lots of information for a *single* character"""
        uri = uriForSearch(kanji, filter="kanji")
        self._extract_html(uri)
        return self.parse_kanji_page_data(kanji, depth)

    def searchForExamples(self, phrase):
        """Return """
        uri = uriForSearch(phrase, filter="sentences")
        self._extract_html(uri)
        return parse_example_page_data(self.html, phrase)

    def scrapeForPhrase(self, phrase):
        uri = uri_for_phrase_scrape(phrase)
        response = requests.get(uri)
        return parsePhrasePageData(response.content, phrase)


    def contains_kanji_glyph(self, kanji):
        kanjiGlyphToken = f'<h1 class="character" data-area-name="print" lang="ja">{kanji}</h1>'
        return kanjiGlyphToken in str(self.html)


    def _get_int_between_strings(self, start_string, end_string):
        string_between_strings = get_string_between_strings(self.html, start_string, end_string)
        return int(string_between_strings) if string_between_strings else None

    def _get_newspaper_frequency_rank(self):
        frequency_section = get_string_between_strings(self.html, '<div class="frequency">', '</div>')
        return get_string_between_strings(frequency_section, '<strong>', '</strong>') if frequency_section else None

    def _get_yomi(self, page_html, yomiLocatorSymbol):
        yomi_section = get_string_between_strings(self.html, f'<dt>{yomiLocatorSymbol}:</dt>', '</dl>')
        return parseAnchorsToArray(yomi_section) or ''


    def get_kunyomi(self):
        return self._get_yomi(self.html, KUNYOMI_LOCATOR_SYMBOL)


    def get_onyomi(self):
        return self._get_yomi(self.html, ONYOMI_LOCATOR_SYMBOL)


    def _get_yomi_examples(self, yomiLocatorSymbol):
        locator_string = f'<h2>{yomiLocatorSymbol} reading compounds</h2>'
        example_section = get_string_between_strings(self.html, locator_string, '</ul>')
        if not example_section:
            return []

        regex = r'<li>(.*?)</li>'
        regex_results = map(lambda x: x.strip(), re.findall(regex, example_section, re.DOTALL))

        for example in regex_results:
            example_lines = list(map(lambda x: x.strip(), example.split('\n')))

            yield {
                'example': example_lines[0],
                'reading': example_lines[1].replace('【', '').replace('】', ''),
                'meaning': html.unescape(example_lines[2]),
            }


    def get_onyomi_examples(self):
        return self._get_yomi_examples(ONYOMI_LOCATOR_SYMBOL)


    def get_kunyomi_examples(self):
        return self._get_yomi_examples(KUNYOMI_LOCATOR_SYMBOL)


    def get_radical(self):
        radicalMeaningStartString = '<span class="radical_meaning">'
        radicalMeaningEndString = '</span>'

        radicalMeaning = self.html.select_one("span.radical_meaning")

        # TODO: Improve this? I don't like all the string finding that much, rather do it with BS finding
        if radicalMeaning:
            page_html_string = str(self.html)

            radicalMeaningStartIndex = page_html_string.find(radicalMeaningStartString)

            radicalMeaningEndIndex = page_html_string.find(radicalMeaningEndString, radicalMeaningStartIndex)

            radicalSymbolStartIndex = radicalMeaningEndIndex + len(radicalMeaningEndString)
            radicalSymbolEndString = '</span>'
            radicalSymbolEndIndex = page_html_string.find(radicalSymbolEndString, radicalSymbolStartIndex)

            radicalSymbolsString = page_html_string[radicalSymbolStartIndex:radicalSymbolEndIndex].replace("\n", '').strip()

            if len(radicalSymbolsString) > 1:
                radicalForms = radicalSymbolsString[1:].replace('(', '').replace(')', '').strip().split(', ')

                return {'symbol': radicalSymbolsString[0], 'forms': radicalForms, 'meaning': radicalMeaning.string.strip()}

            return {'symbol': radicalSymbolsString, 'meaning': radicalMeaning.text.replace("\n", '').strip()}

        return None


    def getParts(self):
        partsSection = self.html.find("dt", text="Parts:").find_next_sibling('dd')
        result = parseAnchorsToArray(str(partsSection))
        result.sort()
        return result


    def get_svg_uri(self):
        svgRegex = re.compile(r"var url = \'//(.*?cloudfront\.net/.*?.svg)")
        regexResult = svgRegex.search(str(self.html))
        return f'https://{regexResult[1]}' if regexResult else None



    def parse_kanji_page_data(self, kanji, depth):
        result = {'query': kanji, 'found': self.contains_kanji_glyph(kanji)}
        if not result['found']:
            return result


        result['taughtIn'] = get_string_between_strings(self.html, 'taught in <strong>', '</strong>')
        result['jlptLevel'] = get_string_between_strings(self.html, 'JLPT level <strong>', '</strong>')
        result['newspaperFrequencyRank'] = self._get_newspaper_frequency_rank()
        result['strokeCount'] = self._get_int_between_strings('<strong>', '</strong> strokes')

        result['meaning'] = html.unescape(
            get_string_between_strings(self.html, '<div class="kanji-details__main-meanings">', '</div>')).strip().replace("\n", '')

        result['kunyomi'] = self.get_kunyomi()
        result['onyomi'] = self.get_onyomi()
        result['onyomiExamples'] = list(self.get_onyomi_examples())
        result['kunyomiExamples'] = list(self.get_kunyomi_examples())
        result['radical'] = self.get_radical()
        result['parts'] = self.getParts()
        result['strokeOrderDiagramUri'] = getUriForStrokeOrderDiagram(kanji)
        result['strokeOrderSvgUri'] = self.get_svg_uri()
        result['strokeOrderGifUri'] = getGifUri(kanji)
        result['uri'] = uriForSearch(kanji, filter="kanji")
        return result

    def _extract_html(self, url):
        """With the response, extract the HTML and store it into the object."""
        self.response = requests.get(url, timeout=5)
        self.html = BeautifulSoup(self.response.content, "lxml") if self.response.ok else None
        # return self.html

    def searchForWord(self, word, depth="shallow"):
        """Take a japanese word and spit out well-formatted dictionaries for each entry.
        
        """

        # self._get_search_response(word)
        self._extract_html(uriForSearch(word))

        results = self.html.select(".concept_light.clearfix")
        # print(results)
        fmtd_results = []

        if depth == "shallow":
            for r in results:
                fmtd_results.append(self._extract_dictionary_information(r))

        elif depth == "deep":

            for r in results:
                fmtd_results.append(self._extract_dictionary_information(r))

                # If there are more than 20 results on the page, there is no "More Words" link
            more = self.html.select_one(".more")

            while more:
                link = more.get("href")
                response = requests.get(r"http:" + link, timeout=5)
                html = BeautifulSoup(response.content, "html.parser")
                results = html.select(".concept_light.clearfix")

                for r in results:
                    fmtd_results.append(self._extract_dictionary_information(r))

                more = html.select_one(".more")

        return fmtd_results

    def _isolate_meanings(self, meanings_list):
        """Take the meanings list from the DOM and clean out non-informative meanings."""

        index = self._get_meaning_cutoff_index(meanings_list)

        if index:
            return [m for i, m in enumerate(meanings_list) if i < index]
        else:
            return meanings_list

    def _get_meaning_cutoff_index(self, meanings_list):
        """Takes a meaning list and extracts all the non Wiki, note, or non-definition entries."""
        try:
            wiki_index = [m.text == "Wikipedia defintiion" for m in meanings_list].index(True)
        except ValueError:
            wiki_index = False

        try:
            other_forms_index = [m.text == "Other forms" for m in meanings_list].index(True)
        except ValueError:
            other_forms_index = False

        try:
            notes_index = [m.text == "Notes" for m in meanings_list].index(True)
        except ValueError:
            notes_index = False

        return wiki_index or other_forms_index or notes_index or None

    def _extract_dictionary_information(self, entry):
        """Take a dictionary entry from Jisho and return all the necessary information."""
        # Clean up the furigana for the result
        furigana = "".join([f.text for f in entry.select(".kanji")])

        # Cleans the vocabulary word for the result
        vocabulary = self._get_full_vocabulary_string(entry) if not entry.select(".concept_light-representation .furigana rt") else entry.select_one(".concept_light-representation .furigana rt").text

        # The fact that this needs to exist is really annoying.
        # If you go to a page like this: https://jisho.org/word/%E5%8D%B0%E5%BA%A6
        # you'll see that this is a word whose furigana is actually in katakana
        # I didn't realize this happens (it makes sense now), and the huge issue
        # is that there's different HTML in this case, so the previous parsing method
        # doesn't work, so we need a new method...

        # Now there could be *really* weird cases where there's a word with both
        # katakana furigana and hiragana furigana (which would be cool), but tbh this
        # I'm satisfied with assuming the whole word corresponds with the whole furigana.

        # Grab the difficulty tags for the result
        diff_tags = [m.text for m in entry.select(".concept_light-tag.label")]

        # Grab each of the meanings associated with the result
        cleaned_meanings = self._isolate_meanings(entry.select_one(".meanings-wrapper"))
        meanings = [m.select_one(".meaning-meaning") for m in cleaned_meanings]
        meanings_texts = [m.text for m in meanings if m != None]

        # Romanize the furigana
        halpern = kana_to_halpern(furigana)

        information = {
            "furigana": furigana,
            "vocabulary": vocabulary,
            "difficulty_tags": diff_tags,
            "meanings": dict(zip(range(1, len(meanings_texts) + 1), meanings_texts)),
            "n_meanings": len(meanings_texts),
            "halpern": halpern
        }

        return information

    def _get_full_vocabulary_string(self, html):
        """Return the full furigana of a word from the html."""
        # The kana represntation of the Jisho entry is contained in this div
        text_markup = html.select_one(".concept_light-representation")

        upper_furigana = text_markup.select_one(".furigana").find_all('span')

        # inset_furigana needs more formatting due to potential bits of kanji sticking together
        inset_furigana_list = []
        # For some reason, creating the iterator "inset_furigana" and then accessing it here
        # causes it to change, like observing it causes it to change. I feel like Schrodinger
        for f in text_markup.select_one(".text").children:
            cleaned_text = f.string.replace("\n", "").replace(" ", "")
            if cleaned_text == "":
                continue
            elif len(cleaned_text) > 1:
                for s in cleaned_text:
                    inset_furigana_list.append(s)
            else:
                inset_furigana_list.append(cleaned_text)

        children = zip_longest(upper_furigana, inset_furigana_list)

        full_word = []
        for c in children:
            if c[0].text != '':
                full_word.append(c[0].text)
            elif c[0].text == '' and contains_kana(c[1]):
                full_word.append(c[1])
            else:
                continue

        # print(''.join(full_word))
        # print("====")
        return ''.join(full_word)


if __name__ == '__main__':
    j = Jisho()
    j.searchForKanji("草")
