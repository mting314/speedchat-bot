# OK, Find-a-class-and-Enroll-er

A Discord bot that can quickly look up and report UCLA course information. Also can keep track of enrollment status of classes, and message you when they're change from closed to open, etc.

My attempt at imitating Courscicle for specifically UCLA courses. Also might be nice for browsing around classes, it's quite a bit faster than MyUCLA.

## Commands List

### ~search_class

`~search_class SUBJECT CATALOG [--term TERM]`

Given a class name (subject + catalog number, i.e. MATH 151AH or COM SCI 32), spit out lots of revelant information.

![search_class](images/Search.png)

If term isn't provided, defaults to whatever the default term is set to.

Then, asks user to react with an emoji choice, corresponding to whatever class they want to add to their watchlist.

### ~display_class

`~display_class SUBJECT CATALOG [--term TERM]`

Very similar

