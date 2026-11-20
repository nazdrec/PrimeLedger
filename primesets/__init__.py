"""PrimeLedger: a local, read-only companion for Warframe prime parts.

The package never touches the game: it works only with an inventory list the
user supplies (screenshots they made themself, read by the AI service of their
choice, or manual input) and with public data from warframe.market and the
official Digital Extremes drop tables.
"""

# The name of the program: the window, the exe, the folder of the user's files, the User-Agent,
# the message for a seller.  It is written here and nowhere else in the code (the Python package
# keeps its first name).
APP_NAME = "PrimeLedger"
# The page of the project, once it has one (https://github.com/<user>/<repo>): goes into the
# User-Agent, so that the services the app talks to can find who made it.
HOMEPAGE = "https://github.com/nazdrec/PrimeLedger"

__version__ = "1.0.1"
