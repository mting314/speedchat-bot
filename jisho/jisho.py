import requests
from itertools import zip_longest
from bs4 import BeautifulSoup
from .kana import *
import re
import urllib
import html

ONYOMI_LOCATOR_SYMBOL = 'On'
KUNYOMI_LOCATOR_SYMBOL = 'Kun'

JISHO_API = 'https://jisho.org/api/v1/search/words'
SCRAPE_BASE_URI = 'https://jisho.org/search/'
STROKE_ORDER_DIAGRAM_BASE_URI = 'https://classic.jisho.org/static/images/stroke_diagrams/'


def remove_new_lines(my_string):
    return re.sub('/(?:\r|\n)/g', '', my_string).strip()


# I'm 99% sure this is bugged/doesn't work anymore because classic.jisho.org doesn't seem to exist anymore
def getUriForStrokeOrderDiagram(kanji):
    return f'{STROKE_ORDER_DIAGRAM_BASE_URI}{str(ord(kanji))}_frames.png'


def uriForKanjiSearch(kanji):
    return f'{SCRAPE_BASE_URI}{urllib.parse.quote(kanji)}%23kanji'


def contains_kanji_glyph(page_html, kanji):
    kanjiGlyphToken = f'<h1 class="character" data-area-name="print" lang="ja">{kanji}</h1>'
    return kanjiGlyphToken in str(page_html)


def get_string_between_strings(data, start_string, end_string):
    regex = f'{re.escape(start_string)}(.*?){re.escape(end_string)}'
    # Need DOTALL because the HTML still has its newline characters
    match = re.search(regex, str(data), re.DOTALL)

    return match[1] if match is not None else None


def getNewspaperFrequencyRank(page_html):
    frequency_section = get_string_between_strings(page_html, '<div class="frequency">', '</div>')
    return frequency_section if get_string_between_strings(frequency_section, '<strong>', '</strong>') else None


def getIntBetweenStrings(page_html, start_string, end_string):
    string_between_strings = get_string_between_strings(page_html, start_string, end_string)
    return int(string_between_strings) if string_between_strings else None


def parseAnchorsToArray(my_string):
    regex = '<a href=".*?">(.*?)<\/a>'
    return re.findall(regex, my_string)


def get_yomi(page_html, yomiLocatorSymbol):
    yomi_section = get_string_between_strings(page_html, f'<dt>{yomiLocatorSymbol}:</dt>', '</dl>')
    return parseAnchorsToArray(yomi_section) or ''


def get_kunyomi(page_html):
    return get_yomi(page_html, KUNYOMI_LOCATOR_SYMBOL)


def get_onyomi(page_html):
    return get_yomi(page_html, ONYOMI_LOCATOR_SYMBOL)


def get_yomi_examples(page_html, yomiLocatorSymbol):
    locator_string = f'<h2>{yomiLocatorSymbol} reading compounds</h2>'
    example_section = get_string_between_strings(page_html, locator_string, '</ul>')
    if not example_section:
        return []

    regex = '<li>(.*?)<\/li>'
    regex_results = map(lambda x: x.strip(), re.findall(regex, example_section, re.DOTALL))

    for example in regex_results:
        example_lines = list(map(lambda x: x.strip(), example.split('\n')))

        yield {
            'example': example_lines[0],
            'reading': example_lines[1].replace('【', '').replace('】', ''),
            'meaning': html.unescape(example_lines[2]),
        }


def get_onyomi_examples(page_html):
    return get_yomi_examples(page_html, ONYOMI_LOCATOR_SYMBOL)


def get_kunyomi_examples(page_html):
    return get_yomi_examples(page_html, KUNYOMI_LOCATOR_SYMBOL)


def get_radical(page_html):
    radicalMeaningStartString = '<span class="radical_meaning">'
    radicalMeaningEndString = '</span>'
    #
    # radicalMeaning = get_string_between_strings(page_html, radicalMeaningStartString, radicalMeaningEndString).strip()

    radicalMeaning = page_html.find("span", {"class", "radical_meaning"})

    # TODO: Improve this? I don't like all the string finding that much, rather do it with BS finding
    if radicalMeaning:
        page_html_string = str(page_html)

        radicalMeaningStartIndex = page_html_string.find(radicalMeaningStartString)

        radicalMeaningEndIndex = page_html_string.find(radicalMeaningEndString, radicalMeaningStartIndex)

        radicalSymbolStartIndex = radicalMeaningEndIndex + len(radicalMeaningEndString)
        radicalSymbolEndString = '</span>'
        radicalSymbolEndIndex = page_html_string.find(radicalSymbolEndString, radicalSymbolStartIndex)

        radicalSymbolsString = page_html_string[radicalSymbolStartIndex:radicalSymbolEndIndex]

        if len(radicalSymbolsString) > 1:
            radicalForms = radicalSymbolsString[1:].replace('(', '').replace(')', '').strip().split(', ')

            return {'symbol': radicalSymbolsString[0], 'forms': radicalForms, 'meaning': radicalMeaning.string.strip()}

        return {'symbol': radicalSymbolsString, 'meaning': radicalMeaning}

    return None


def getParts(page_html):
    partsSection = page_html.find("dt", text="Parts:").find_next_sibling('dd')
    result = parseAnchorsToArray(str(partsSection))
    result.sort()
    return result


def get_svg_uri(page_html):
    svgRegex = '/\/\/.*?.cloudfront.net\/.*?.svg/'
    regexResult = re.search(svgRegex, str(page_html))
    return f'https:{regexResult[0]}' if regexResult else None


def getGifUri(kanji):
    for char in kanji:
        fileName = f'{str(ord(char))}.gif'
        animationUri = f'https://raw.githubusercontent.com/mistval/kanji_images/master/gifs/{fileName}'
        yield animationUri


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


def parse_kanji_page_data(page_html, kanji):
    result = {'query': kanji, 'found': contains_kanji_glyph(page_html, kanji)}
    if not result['found']:
        return result

    result['taughtIn'] = get_string_between_strings(page_html, 'taught in <strong>', '</strong>')
    result['jlptLevel'] = get_string_between_strings(page_html, 'JLPT level <strong>', '</strong>')
    result['newspaperFrequencyRank'] = getNewspaperFrequencyRank(page_html)
    result['strokeCount'] = getIntBetweenStrings(page_html, '<strong>', '</strong> strokes')
    result['meaning'] = html.unescape(remove_new_lines(
        get_string_between_strings(page_html, '<div class="kanji-details__main-meanings">', '</div>')).strip())
    result['kunyomi'] = get_kunyomi(page_html)
    result['onyomi'] = get_onyomi(page_html)
    result['onyomiExamples'] = list(get_onyomi_examples(page_html))
    result['kunyomiExamples'] = list(get_kunyomi_examples(page_html))
    result['radical'] = get_radical(page_html)
    result['parts'] = getParts(page_html)
    result['strokeOrderDiagramUri'] = getUriForStrokeOrderDiagram(kanji)
    result['strokeOrderSvgUri'] = get_svg_uri(page_html)
    result['strokeOrderGifUri'] = list(getGifUri(kanji))
    result['uri'] = uriForKanjiSearch(kanji)
    return result


kanjiRegex = '[\u4e00-\u9faf\u3400-\u4dbf]'


def uriForExampleSearch(phrase):
    return f'{SCRAPE_BASE_URI}{urllib.parse.quote(phrase)}%23sentences'


def getKanjiAndKana(div):
    ul = div.find_all('ul')[0]
    # contents = ul.contents()

    kanji = ''
    kana = ''
    for child in ul.children:
        # content = contents.eq(i)
        if child.name == 'li':
            li = child
            furigana = li.find("span", {"class", 'furigana'}).text if li.find("span", {"class",
                                                                                       'furigana'}) is not None else None
            unlifted = li.find("span", {"class", 'unlinked'}).text if li.find("span", {"class",
                                                                                       'unlinked'}) is not None else None

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
    pieceElements = sentenceElement.find_all("li", {"class", "clearfix"}) + sentenceElement.find_all("el")
    pieces = []

    for pieceElement in pieceElements:
        # pieceElement = pieceElements.eq(pieceIndex)
        if pieceElement.name == 'li':
            pieces.append({
                'lifted': pieceElement.find("span", {"class", 'furigana'}).text if pieceElement.find("span", {"class",
                                                                                                              'furigana'}) is not None else '',
                'unlifted': pieceElement.find("span", {"class", 'unlinked'}).text if pieceElement.find("span", {"class",
                                                                                                                'unlinked'}) is not None else '',
            })
        else:
            pieces.append({
                'lifted': '',
                'unlifted': pieceElement.text,
            })

    return pieces


def parseExampleDiv(div):
    english = str(div.find('span', {"class", 'english'}).find(text=True))
    kanji, kana = getKanjiAndKana(div)

    return english, kanji, kana, getPieces(div)


def parseExamplePageData(pageHtml, phrase):
    string_page_html = str(pageHtml)
    pageHtmlReplaced = re.sub(
        '<\/li>\s*([^\s<>]+)\s*<li class="clearfix">/g', r'</li><el>\1</el><li class="clearfix">', string_page_html)
    myhtml = BeautifulSoup(pageHtmlReplaced, 'lxml')
    divs = myhtml.find_all("div", {"class", 'sentence_content'})

    results = []
    for div in divs:
        # div = divs.eq(i)
        results.append(parseExampleDiv(div))

    return {
        'query': phrase,
        'found': len(results) > 0,
        'result': results,
        'uri': uriForExampleSearch(phrase),
        'phrase': phrase
    }


# PHRASE SCRAPE FUNCTIONS START

def getTags(my_html):
    tags = []

    tagElements = my_html.find_all("span", {"class", 'concept_light-tag'})
    for tagElement in tagElements:
        # tagText = tagElements.eq(i).text()
        tags.append(tagElement.text)

    return tags


def getMeaningsOtherFormsAndNotes(my_html):
    otherForms = []
    notes = []

    meaningsWrapper = my_html.select(
        '#page_container > div > div > article > div > div.concept_light-meanings.medium-9.columns > div')[0]
    meaningsChildren = meaningsWrapper.children
    meanings = []

    mostRecentWordTypes = []
    for child in meaningsChildren:
        # child = meaningsChildren.eq(meaningIndex)
        if child.get("class")[0] == 'meaning-tags':
            mostRecentWordTypes = map(lambda x: x.strip().lower(), child.text.split(','))
        elif mostRecentWordTypes[0] == 'other forms':
            otherForms = list(map(lambda y: ({'kanji': y[0], 'kana': y[1]}),
                                  map(lambda x: x.replace('【', '').replace('】', '').split(' '),
                                      child.text.split('、'))))
        elif mostRecentWordTypes[0] == 'notes':
            notes = child.text().split('\n')
        else:
            meaning = child.find('.meaning-meaning').text()
            meaningAbstract = child.find('.meaning-abstract').find('a').remove().end().text()

            supplemental = filter(lambda y: bool(y),
                                  map(lambda x: x.strip(), child.find('.supplemental_info').text().split(',')))

            seeAlsoTerms = []
            for i in reversed(range(len(supplemental))):
                supplementalEntry = supplemental[i]
                if supplementalEntry.startswith('See also'):
                    seeAlsoTerms.append(supplementalEntry.replace('See also ', ''))
                    supplemental.pop(i)

            sentences = []
            sentenceElements = child.find('.sentences').children('.sentence')

            for sentenceElement in sentenceElements:
                # sentenceElement = sentenceElements.eq(sentenceIndex)

                english = sentenceElement.find('.english').text()
                pieces = getPieces(sentenceElement)

                japanese = sentenceElement.find('.english').remove().end().find('.furigana').remove().end().text();

                sentences.append({english, japanese, pieces})

            meanings.append({
                'seeAlsoTerms': seeAlsoTerms,
                'sentences': sentences,
                'definition': meaning,
                'supplemental': supplemental,
                'definitionAbstract': meaningAbstract,
                'tags': mostRecentWordTypes,
            })

    return meanings, otherForms, notes


def uriForPhraseScrape(searchTerm):
    return f'https://jisho.org/word/{urllib.parse.quote(searchTerm)}'


def parsePhrasePageData(pageHtml, query):
    my_html = BeautifulSoup(pageHtml, "lxml")
    meanings, otherForms, notes = getMeaningsOtherFormsAndNotes(my_html)

    result = {
        'found': True,
        'query': query,
        'uri': uriForPhraseScrape(query),
        'tags': getTags(my_html),
        'meanings': meanings,
        'other_forms': otherForms,
        'notes': notes
    }

    return result


class Jisho:
    """A class to interface with Jisho.org and store search results for use.

    """

    JISHO_API = 'https://jisho.org/api/v1/search/words'
    SCRAPE_BASE_URI = 'https://jisho.org/search/'
    STROKE_ORDER_DIAGRAM_BASE_URI = 'https://classic.jisho.org/static/images/stroke_diagrams/'

    def __init__(self):
        self.html = None
        self.response = None

    def searchForKanji(self, kanji):
        uri = uriForKanjiSearch(kanji)
        page = requests.get(uri)
        soup = BeautifulSoup(page.content, 'lxml')
        return parse_kanji_page_data(soup, kanji)

    def searchForExamples(self, phrase):
        uri = uriForExampleSearch(phrase)
        page = requests.get(uri)
        soup = BeautifulSoup(page.content, 'lxml')
        return parseExamplePageData(soup, phrase)

    @staticmethod
    async def scrapeForPhrase(phrase):
        uri = uriForPhraseScrape(phrase)
        try:
            response = requests.get(uri)
            return parsePhrasePageData(response.content, phrase)
        except Exception as err:
            # if err.response.status == 404:
            #     return {
            #         'query': phrase,
            #         'found': False,
            #     }

            raise err

    def contains_kana(self, word):
        """Takes a word and returns true if there are hiragana or katakana present within the word"""
        for k in word:
            if k in hiragana or k in katakana or k in small_characters:
                return True
        return False

    def _get_search_response(self, word="", filters=["words"]):
        """Takes a word, stores it within the Jisho object, and returns parsed HTML"""
        base_url = r"https://jisho.org/search/"

        # Take all the filters and append them to the base_url
        base_url += word
        for filter in filters:
            base_url += r"%20%23" + filter
        # print(base_url + word)
        self.response = requests.get(base_url + word, timeout=5)
        return self.response

    def _extract_html(self):
        """With the response, extract the HTML and store it into the object."""
        self.html = BeautifulSoup(self.response.content, "html.parser")
        return self.html

    def jsearch(self, word, filters=["words"], depth="shallow"):
        """Take a japanese word and spit out well-formatted dictionaries for each entry.
        
        """

        self._get_search_response(word, filters)
        self._extract_html()

        results = self.html.find_all(class_="concept_light clearfix")
        # print(results)
        fmtd_results = []

        if depth == "shallow":
            for r in results:
                fmtd_results.append(self._extract_dictionary_information(r))

        elif depth == "deep":

            for r in results:
                fmtd_results.append(self._extract_dictionary_information(r))

                # If there are more than 20 results on the page, there is no "More Words" link
            more = self.html.find(class_="more")

            while more:
                link = more.get("href")
                response = requests.get(r"http:" + link, timeout=5)
                html = BeautifulSoup(response.content, "html.parser")
                results = html.find_all(class_="concept_light clearfix")

                for r in results:
                    fmtd_results.append(self._extract_dictionary_information(r))

                more = html.find(class_="more")

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
        # if wiki_index:
        #     return wiki_index
        # elif other_forms_index:
        #     return other_forms_index
        # elif notes_index:
        #     return notes_index
        # else:
        #     return None

    def _extract_dictionary_information(self, entry):
        """Take a dictionary entry from Jisho and return all the necessary information."""
        # Clean up the furigana for the result
        furigana = "".join([f.text for f in entry.find_all(class_="kanji")])

        # Cleans the vocabulary word for the result
        vocabulary = self._get_full_vocabulary_string(entry)

        # Grab the difficulty tags for the result
        diff_tags = [m.text for m in entry.find_all(class_="concept_light-tag label")]

        # Grab each of the meanings associated with the result
        cleaned_meanings = self._isolate_meanings(entry.find(class_="meanings-wrapper"))
        meanings = [m.find(class_="meaning-meaning") for m in cleaned_meanings]
        meanings_texts = [m.text for m in meanings if m != None]

        # Romanize the furigana
        # halpern = self.kana_to_halpern(furigana)

        information = {
            "furigana": furigana,
            "vocabulary": vocabulary,
            "difficulty_tags": diff_tags,
            "meanings": dict(zip(range(1, len(meanings_texts) + 1), meanings_texts)),
            "n_meanings": len(meanings_texts),
            # "halpern": halpern
        }

        return information

    def _get_full_vocabulary_string(self, html):
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
            elif c[0].text == '' and self.contains_kana(c[1]):
                full_word.append(c[1])
            else:
                continue

        # print(''.join(full_word))
        # print("====")
        return ''.join(full_word)


if __name__ == '__main__':
    j = Jisho()
    j.get_stroke_order("草")
