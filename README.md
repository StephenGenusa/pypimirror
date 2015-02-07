pypimirror
==========

Modifications April 2014 by Stephen Genusa
<p>
<ol>
<li>Saves pickled packages list to help debugging and/or restarting process using the same package sequence
<li>Improved error handling in a couple of functions to prevent premature exit of script
<li>Fixed problem with HTTP requests to sourceforge.net when files no longer exist
</ol>

Modifications February 2015 by Stephen Genusa
<ol>
<li>Saves a filtered list to a pickled file to deal with an exception that is being trapped (somewhere) but not 
handled causing the script to halt without any indication. The pickled filter file allows me to restart the process where it left off, lowering time and wasted bandwidth
<li>Downloaded archives are now timestamped to the newest file contained in the archive rather than the date/time it was downloaded
<li>Info.html is saved only if PyPi's html file is larger than the one already saved to the local mirror
</ol>
