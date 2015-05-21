#pypimirror

Modifications April 2014

1. Saves pickled packages list to help debugging and/or restarting process using the same package sequence
2. Improved error handling in a couple of functions to prevent premature exit of script
3. Fixed problem with HTTP requests to sourceforge.net when files no longer exist


Modifications February 2015

1. Saves a filtered list to a pickled file to deal with an exception that is being trapped (somewhere) but not 
handled causing the script to halt without any indication. The pickled filter file allows me to restart the process where it left off, lowering time and wasted bandwidth
2. Downloaded archives are now timestamped to the newest file contained in the archive rather than the date/time it was downloaded
3. Info.html is saved only if PyPi's html file is larger than the one already saved to the local mirror

Modifications March 2015

1. Saves DOAP XML file for current package
2. -H param added to set incremental fetch update time by hours
3. -a param determines hours since last update (based on the date/time of the log) and begins fetch at that point in time

Modifications May 2015

1. urllib2.urlopen has finally died the death due to SSL changes on PyPi. I've done a rough replacement of urlopen with the requests module to get the utility functioning again. More cleanup is needed now but it is back in business.
2. (a) Adds a final / to the end of the 'simple' URL (b) also calls .lower() on the package name and (c) changed http to https to end the -3- unnecessary 301 redirects and just get the files we want on the first call



##Usage
<pre><code>
Options:
  -h, --help            show this help message and exit
  -v, --verbose         verbose on
  -f LOG_FILENAME, --log-filename=LOG_FILENAME
                        Name of logfile
  -I, --initial-fetch   Initial PyPI mirror fetch
  -U, --update-fetch    Perform incremental update of the mirror
  -c, --log-console     Also log to console
  -i, --indexes-only    create indexes only (no mirroring)
  -e, --follow-external-links
                        Follow and download external links)
  -x, --follow-external-index-pages
                        Follow external index pages and scan for links
  -d FETCH_SINCE_DAYS, --fetch-since-days=FETCH_SINCE_DAYS
                        Days in past to fetch for incremental update
  -H FETCH_SINCE_HOURS, --fetch-since-hours=FETCH_SINCE_HOURS
                        Hours in past to fetch for incremental update
  -a, --autocalc        Automatically calc how many hours since last run and
                        fetch based on that time
  -n, --nonstop         nonstop loop
  -r, --restart         restart with clean indexes
</code></pre>  
