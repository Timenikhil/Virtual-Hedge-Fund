# quantrocket.countdown.crontab.sh
#
# This crontab file defines the schedule for running commands. (All example
# commands are currently commented out).
#
# Usage guide: http://qrok.it/p/schedule
#
# Crontab syntax cheat sheet
# .------------ minute (0 - 59)
# |   .---------- hour (0 - 23)
# |   |   .-------- day of month (1 - 31)
# |   |   |   .------ month (1 - 12) OR jan,feb,mar,apr ...
# |   |   |   |   .---- day of week (0 - 6) (Sunday=0 or 7)  OR sun,mon,tue,wed,thu,fri,sat
# |   |   |   |   |
# *   *   *   *   *   command to be executed

# ---------------
# DATA COLLECTION
# ---------------

# Collect usstock-1min bundle each weekday morning
#0 7 * * mon-fri quantrocket zipline ingest 'usstock-1min'

# Collect Sharadar fundamentals each weekday morning
#0 3 * * mon-fri quantrocket fundamental collect-sharadar-fundamentals

# Collect data from Interactive Brokers each evening at 5:30 PM if the market was open
#30 17 * * mon-fri quantrocket master isopen 'XNYS' --ago '6h' && quantrocket history collect 'arca-etf-30min' --priority

# -------
# TRADING
# -------

# Trade an end-of-day Moonshot strategy each morning at 9 AM
#0 9 * * mon-fri quantrocket master isopen 'XNYS' --in '1h' && quantrocket moonshot trade 'dma' | quantrocket blotter order -f -

# Start up a Zipline strategy each morning at 9:20 AM
#20 9 * * mon-fri quantrocket master isopen 'XNYS' --in '1h' && quantrocket zipline trade 'high-low'

# Collect data and run an intraday FX Moonshot strategy every 5 minutes between
# 8 AM and 8 PM on weekdays
#*/5 8-19 * * mon-fri quantrocket master isopen 'IDEALPRO' && quantrocket history collect 'fx-majors-5min' && quantrocket history wait 'fx-majors-5min' && quantrocket moonshot trade 'fx-revert' | quantrocket blotter order -f '-'

# -----------
# MAINTENANCE
# -----------

# Restart IB Gateway each night
#30 8 * * * quantrocket ibg stop --wait ; quantrocket ibg start

# maintain securities master database by delisting IBKR records periodically;
# see http://qrok.it/p/delist
#0 5 * * sun quantrocket ibg start --wait && quantrocket master get --sec-types 'STK' --vendors 'ibkr' --fields 'Sid' --exclude-delisted | quantrocket master diff-ibkr --infile - --fields 'ibkr_ConId' --delist-missing --delist-exchanges 'VALUE' 'PINK'

# drop old ticks from a real-time database to avoid filling up the disk
#0 6 * * sun quantrocket realtime drop-ticks 'us-stk-tick' --older-than '30d'
