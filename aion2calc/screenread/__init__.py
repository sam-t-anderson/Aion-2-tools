"""Reading the game's Genus Insight and Title windows from the screen (0.2.347).

The official character page carries neither a character's Pet Genus Insight lines nor the titles it
owns, so both were typed into the app by hand. A screen read takes a picture of the game's screen (or
a screenshot the player pastes), reads its text with the optical character recognition built into
Windows, and fills the app's Genus editor or its owned-titles list for the player to check and save:

* ``ocr``: the text on an image, word by word with each word's box, from Windows' own OCR engine
  (``Windows.Media.Ocr`` through pywinrt), offline. Elsewhere it reports itself unavailable.
* ``parse``: which window a picture shows and what it says: a genus, its Insight level and each
  slot's line (names matched against the slot's possible lines, values checked against their ranges),
  or the titles on a page of the Title window (matched against the title catalog), the page's
  "Show unacquired titles only" box and the window's collection count.
* ``capture``: the screen the game is on.
* ``service``: one read from start to finish, the recent reads the app's pages pick up, and the title
  pages read so far.

Nothing is saved to a character until the player saves it in the app.
"""
