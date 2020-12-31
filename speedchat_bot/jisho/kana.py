_readings = [
    "a", "i", "u", "e", "o", "ka", "ki", "ku", "ke", "ko",
    "ga", "gi", "gu", "ge", "go", "sa", "shi", "su", "se", "so",
    "za", "ji", "zu", "ze", "zo", "ta", "chi", "tsu", "te", "to",
    "da", "dzi", "du", "de", "do", "na", "ni", "nu", "ne", "no",
    "ha", "hi", "fu", "he", "ho", "ba", "bi", "bu", "be", "bo",
    "pa", "pi", "pu", "pe", "po", "ma", "mi", "mu", "me", "mo",
    "ya", "yu", "yo", "ra", "ri", "ru", "re", "ro",
    "wa", "wo", "n",
    "kya", "kyu", "kyo", "gya", "gyu", "gyo",
    "sha", "shu", "sho", "ja", "ju", "jo",
    "cha", "chu", "cho", "nya", "nyu", "nyo",
    "hya", "hyu", "hyo", "bya", "byu", "byo",
    "pya", "pyu", "pyo", "mya", "myu", "myo",
    "rya", "ryu", "ryo",
    "",
    "fa", "fi", "fe", "fo",
    "va", "vi", "ve", "vo"
]

hiragana = [
    "あ", "い", "う", "え", "お", "か", "き", "く", "け", "こ",
    "が", "ぎ", "ぐ", "げ", "ご", "さ", "し", "す", "せ", "そ",
    "ざ", "じ", "ず", "ぜ", "ぞ", "た", "ち", "つ", "て", "と",
    "だ", "ぢ", "づ", "で", "ど", "な", "に", "ぬ", "ね", "の",
    "は", "ひ", "ふ", "へ", "ほ", "ば", "び", "ぶ", "べ", "ぼ",
    "ぱ", "ぴ", "ぷ", "ぺ", "ぽ", "ま", "み", "む", "め", "も",
    "や", "ゆ", "よ", "ら", "り", "る", "れ", "ろ",
    "わ", "を", "ん",
    "きゃ", "きゅ", "きょ", "ぎゃ", "ぎゅ", "ぎょ",
    "しゃ", "しゅ", "しょ", "じゃ", "じゅ", "じょ",
    "ちゃ", "ちゅ", "ちょ", "にゃ", "にゅ", "にょ",
    "ひゃ", "ひゅ", "ひょ", "びゃ", "びゅ", "びょ",
    "みゃ", "みゅ", "みょ", "りゃ", "りゅ", "りょ",
    "ぴゃ", "ぴゅ", "ぴょ",
    "ー",
    "ふぁ", "ふぃ", "ふぇ", "ふぉ",
    "ゔぁ", "ゔぃ", "ゔぇ", "ゔぉ"
]

katakana = [
    "ア", "イ", "ウ", "エ", "オ", "カ", "キ", "ク", "ケ", "コ",
    "ガ", "ギ", "グ", "ゲ", "ゴ", "サ", "シ", "ス", "セ", "ソ",
    "ザ", "ジ", "ズ", "ゼ", "ゾ", "タ", "チ", "ツ", "テ", "ト",
    "ダ", "ヂ", "ヅ", "デ", "ド", "ナ", "ニ", "ヌ", "ネ", "ノ",
    "ハ", "ヒ", "フ", "ヘ", "ホ", "バ", "ビ", "ブ", "ベ", "ボ",
    "パ", "ピ", "プ", "ペ", "ポ", "マ", "ミ", "ム", "メ", "モ",
    "ヤ", "ユ", "ヨ", "ラ", "リ", "ル", "レ", "ロ",
    "ワ", "ヲ", "ン",
    "キャ", "キュ", "キョ", "ギャ", "ギュ", "ギョ",
    "シャ", "シュ", "ショ", "ジャ", "ジュ", "ジョ",
    "チャ", "チュ", "チョ", "ニャ", "ニュ", "ニョ",
    "ヒャ", "ヒュ", "ヒョ", "ビャ", "ビュ", "ビョ",
    "ピャ", "ピュ", "ピョ", "ミャ", "ミュ", "ミョ",
    "リャ", "リュ", "リョ",
    "ー",
    "ファ", "フィ", "フェ", "フォ",
    "ヴァ", "ヴィ", "ヴェ", "ヴォ"
]

small_characters = [
    "っ", "ッ",
    "ぁ", "ぃ", "ぅ", "ぇ", "ぉ",
    "ァ", "ィ", "ゥ", "ェ", "ォ"
]

hira = zip(hiragana, _readings)
kata = zip(katakana, _readings)

# Dictionaries for storing kana to English character pairs
hira2eng = dict(zip(hiragana, _readings))
eng2hira = dict(zip(_readings, hiragana))
kata2eng = dict(zip(katakana, _readings))
eng2kata = dict(zip(_readings, katakana))

if __name__ == '__main__':
    print(kata)