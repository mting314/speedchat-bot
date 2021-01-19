# OK, Find-a-class-and-Enroll-er

A Discord bot that can quickly look up and report UCLA course information. Also can keep track of enrollment status of classes, and message you when they're change from closed to open, etc.

My attempt at imitating Courscicle for specifically UCLA courses. Also might be nice for browsing around classes, it's quite a bit faster than MyUCLA.

## Commands List

### ~search_class

`~search_class SUBJECT CATALOG# [fast/slow] [term]`

Given a class name (subject + catalog number, i.e. MATH 151AH or COM SCI 32), spit out lots of revelant information.

There are two modes with this command: `fast` and `slow`. `fast` mode displays an embed:

![fast search](images/search.png)

and `slow` mode goes to the Find a Class and Enroll search page to take a screenshot of 

![slow search](images/search.png)

Defaults to fast mode.

TODO: Defaults whatever the current term is according to MyUCLA?

### ~reload_json
In case you want to re-fetch the list of classes from UCLA's schedule of classes.


