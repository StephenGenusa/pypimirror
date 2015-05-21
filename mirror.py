#! /usr/bin/env python
################################################################
# z3c.pypimirror - A PyPI mirroring solution
# Written by Daniel Kraft, Josip Delic, Gottfried Ganssauge and
# Andreas Jung
#
# Published under the Zope Public License 2.1
################################################################
#
# Modifications April 2014 by Stephen Genusa
# 1) Saves pickled packages list to help debugging and/or
#      restarting process using the same package sequence
# 2) Improved error handling in a couple of functions to
#      prevent premature exit of script
# 3) Fixed problem with sourceforge.net requests where files no 
#      longer exist
#
# Modifications February 2015 by Stephen Genusa
# 1) Saves a filtered list to a pickled file to deal with an
#      exception that is being trapped (somewhere) but not 
#      handled causing the script to halt without any indication
#      The pickled filter file allows me to restart the process
#      where it left off, lowering time and wasted bandwidth
# 2) Downloaded archives are now timestamped to the newest file
#      contained in the archive rather than the date/time it was
#      downloaded
# 3) Info.html is saved only if PyPi's html file is larger than
#      the one already saved to the local mirror
# 4) Added code to save completed position/resume position on restart
#
# Modifications March 2015 by Stephen Genusa
# 1) Saves DOAP XML file for current package
# 2) -H param added to set incremental update time by hours rather than
#      the limited -d Days parameter
# 3) Can determine hours since last update (based on the date/time of the log)
#      using the -a parameter
#
# Example usage:
#   python mirror.py -v -c -U -r -a pypimirror.cfg
#     (verbose, log to console, Update fetch, restart with fresh PyPi package
#      data, automatically determine time to begin refresh from)
#
#
# Modifications May 2015 by Stephen Genusa
# 1) urllib2.urlopen has finally died the death due to SSL changes on PyPi. I've 
#      done a rough replacement of urlopen with the requests module to get the
#      utility functioning again. More cleanup is needed now.
# 2) (a) Adds a final / to the end of the 'simple' URL (b) also calls .lower() on 
#      the package name (c) changed http to https and (d) changes '_' to '-'. These
#      changes put an end to -5- frequent but unnecessary 301 redirects and the 
#      proper URL is now requested on the first call
# 3) Detects when HTML (custom 404 pages) are returned rather than the requested
#      binary package file and does not save these invalid files


# Standard Library Modules
import datetime
import ConfigParser
try: 
    from hashlib import md5
except ImportError:
    from md5 import md5
from glob import fnmatch
import httplib
import linecache
import optparse
import os
import pickle
import pkg_resources # setuptools
import re
import sys
import shutil
import socket
import tempfile
import time
import urllib 
import urllib2
import urlparse
import util
from xml.dom.minidom import parseString
import xmlrpclib

# 3rd Party Project Modules
from BeautifulSoup import BeautifulSoup
import HTMLParser
import requests
import zc.lockfile

# Internal Project Modules
from logger import getLogger
import touch_archives



LOG = None
dev_package_regex = re.compile(r'\ddev[-_]')



def pypimirror_version():
    """
        returns a version string
    """
    version = pkg_resources.working_set.by_key["z3c.pypimirror"].version
    return 'z3c.pypimirror/%s' % version


# http://stackoverflow.com/questions/14519177/python-exception-handling-line-number
def GetExceptionInfo():
    exc_type, exc_obj, tb = sys.exc_info()
    f = tb.tb_frame
    lineno = tb.tb_lineno
    filename = f.f_code.co_filename
    linecache.checkcache(filename)
    line = linecache.getline(filename, lineno, f.f_globals)
    return 'EXCEPTION IN ({}, LINE {} "{}"): {}'.format(filename, lineno, line.strip(), exc_obj)



class Stats(object):
    """ This is just for statistics """
    def __init__(self):
        self._found = []
        self._stored = []
        self._error_404 = []
        self._error_invalid_package = []
        self._error_invalid_url = []
        self._starttime = time.time()

    def runtime(self):
        runtime = time.time() - self._starttime
        if runtime > 60:
            return "%dm%2ds" % (runtime//60, runtime%60)
        return "%ds" % runtime

    def found(self, name):
        self._found.append(name)

    def stored(self, name):
        self._stored.append(name)

    def error_404(self, name):
        self._error_404.append(name)

    def error_invalid_package(self, name):
        self._error_invalid_package.append(name)

    def error_invalid_url(self, name):
        self._error_invalid_url.append(name)

    def getStats(self):
        ret = []
        ret.append("Statistics")
        ret.append("----------")
        ret.append("Found (cached):         %d" % len(self._found))
        ret.append("Stored (downloaded):    %d" % len(self._stored))
        ret.append("Not found (404):        %d" % len(self._error_404))
        ret.append("Invalid packages:       %d" % len(self._error_invalid_package))
        ret.append("Invalid URLs:           %d" % len(self._error_invalid_url))
        ret.append("Runtime:                %s" % self.runtime())
        return ret



class PypiPackageList(object):
    """
        This fetches and represents a package list
    """
    def __init__(self, pypi_xmlrpc_url='http://pypi.python.org/pypi'):
        self._pypi_xmlrpc_url = pypi_xmlrpc_url

    def list(self, filter_by=None, incremental=False, fetch_since_days=7, fetch_since_hours=0):
        print time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()) + (" " * 12) + "Building package list for updates. "+ ("Incremental" if incremental else "Non-Incremental") + \
              (" Fetch since hours=" + str(fetch_since_hours) if fetch_since_hours > 0 else " fetch since days=" + str(fetch_since_days))
        
        socket.setdefaulttimeout(30)
        ##########################################
        # Debug using a single package
        #return ['Custom-Interactive-Console']  
        ##########################################
        #return ['Custom-Interactive-Console']  
        use_pickled_index=True
        strListPickled = 'packages.p'
        server = xmlrpclib.Server(self._pypi_xmlrpc_url)
        if use_pickled_index and os.path.isfile(strListPickled):
            print "Loading packages.p"
            packages = pickle.load(open(strListPickled, 'rb'))
            #return packages[0:2]
        else:
            try:
                packages = server.list_packages()
                if use_pickled_index:
                    pickle.dump(packages, open(strListPickled, 'wb'))
                else:
                    if os.path.isfile(strListPickled):
                        os.remove(strListPickled)
            except Exception, e:
                raise PackageError("General error: %s" % e)
           

        print "   Initial Package Count  = " + str(len(packages))
        
        ##########################################
        # Return all available packages
        #return packages
        ##########################################
        #return packages

        # There is a problem where this program halts with no exception
        # so I am not sure where the code is failing yet.
        # This is a workaround until I locate that problem
        pkg_start_pos = 0
        
        # This first case handles a non-incremental update:
        if not incremental and not use_pickled_index:
            packages = list(set(packages))
            packages = packages[pkg_start_pos:]
            return packages

        # This second case handles the incremental update:
        # If the script finds the incremental package list already
        # built it returns that so that 1) the list does not have to 
        # be rebuilt and 2) you can pickup from the point of failure
        # by changing pkg_start_pos to the last good package number
        # shown in the previous run. You can also do a resume after
        # a CTRL-C
        if incremental:
            strIncrementalPickled = "incremental_" + strListPickled
            if use_pickled_index and os.path.isfile(strIncrementalPickled):
                print "Loading " + strIncrementalPickled
                packages = pickle.load(open(strIncrementalPickled, 'rb'))
                packages = packages[pkg_start_pos:]
                print "Incremental Package Count = " + str(len(packages))
                return packages
        
        filtered_packages = []
        for package in packages:
            if len(filter_by) > 0:
                if not True in [fnmatch.fnmatch(package, f) for f in filter_by]:
                    continue
                filtered_packages.append(package)
            else:
                filtered_packages.append(package)
        print "   Filtered Package Count = " + str(len(filtered_packages))
         
        if incremental:
            if fetch_since_hours > 0:
               changelog = server.changelog(int(time.time() - fetch_since_hours*3600))
            else:
               changelog = server.changelog(int(time.time() - fetch_since_days*24*3600))
            changed_packages = [tp[0] for tp in changelog 
                                if 'file' in tp[3]]
            changed_packages = [package for package in changed_packages if package in filtered_packages]
            changed_packages = list(set(changed_packages))
            print "Incremental Package Count = " + str(len(changed_packages))
            if use_pickled_index:
                pickle.dump(changed_packages, open("incremental_" + strListPickled, 'wb'))
            return changed_packages
        else:
            filtered_packages = list(set(filtered_packages))
            print "Filtered Package Count(2) = " + str(len(filtered_packages))
            return filtered_packages
    

class PackageError(Exception):
    try:
        raise Exception
    except Exception, e:
       print e.message
    pass

class Package(object):
    """
        This handles the list of versions and fetches the
        files
    """
    def __init__(self, package_name, pypi_base_url="https://pypi.python.org/simple"):
        self._links_cache = None

        if not util.isASCII(package_name):
            raise PackageError("%s is not a valid package name." % package_name)

        try:
            package_name = urllib.quote(package_name)
        except KeyError:
            raise PackageError("%s is not a valid package name." % package_name)

        self.name = package_name
        self._pypi_base_url = pypi_base_url

    def url(self, filename=None, splittag=True):
        if filename:
            (filename, rest) = urllib.splittag(filename)
            try:
                filename = urllib.quote(filename)
            except KeyError:
                raise PackageError("%s is not a valid filename." % filename)
        url = "%s/%s/" % (self._pypi_base_url, self.name.lower().replace('_', '-'))
        #print "--> ", url
        if filename:
            url = "%s/%s" % (url, filename)
        return url

    def _fetch_index(self):
       #print "in _fetch_index"
       try:
           r = requests.get('https://pypi.python.org/pypi/' + self.name + '/')
           raw_html = r.content          
           
           
           if raw_html.find('Index of Packages') > -1:
              try:
                 soup = BeautifulSoup(raw_html)
                 links = soup.findAll("a")
                 for link in links:
                    href = link.get("href")
                    if href != None and href.find('/pypi/' + self.name + '/') > -1:
                       r = requests.get('https://pypi.python.org' + href)
                       raw_html = r.content 
                       break
              except:
                 LOG.debug("HTML download error " + href)
              
           
           # Save the raw_html
           if not os.path.exists(local_pypi_path + self.name):
               os.mkdir(local_pypi_path + self.name)
           html_info_filename = os.path.join(local_pypi_path, self.name, "info.html")
           html_orig_info_filename = os.path.join(local_pypi_path, self.name, "info_orig.html")
           if not os.path.isfile(html_orig_info_filename) and os.path.isfile(html_info_filename):
              os.rename(html_info_filename, html_orig_info_filename)
           if (os.path.isfile(html_info_filename) and len(raw_html) >= os.path.getsize(html_info_filename)) or not os.path.isfile(html_info_filename):
               open(html_info_filename, "wb").write(raw_html)
               LOG.debug("HTML info file written " + html_info_filename)

           # Save Current XML DOAP Record   
           try:
             soup = BeautifulSoup(raw_html)
             links = soup.findAll("a")
             for link in links:
                href = link.get("href")
                if href != None and href.find('action=doap') > -1:
                   xml_filename = href.replace('/pypi?:action=doap&name=', '').replace('&version=', '-') + '.xml'
                   xml_info_filename = os.path.join(local_pypi_path, self.name, xml_filename)
                   if not os.path.isfile(xml_info_filename):
                      r = requests.get('https://pypi.python.org' + href.replace(' ', '%20')) 
                      raw_xml = r.content
                      open(xml_info_filename, "wb").write(raw_xml)
                      LOG.debug("XML info file written " + xml_info_filename)
                      dom3 = parseString(raw_xml)
                      LOG.debug('*' * 3 + ' ' + dom3.getElementsByTagName('shortdesc')[0].firstChild.data + ' ' + '*' * 3)                     
                   break
           except:
             LOG.debug("XML download error " + href)
               
               
       except Exception, e:
           raise PackageError('Generic error: %s' % e)
       #print "in _fetch_index"
       try:
           r = requests.get(self.url())
           html = r.content
       except urllib2.HTTPError, v:
           if '404' in str(v):             # sigh
               raise PackageError("Package not available (404): %s" % self.url())
           raise PackageError("Package not available (unknown reason): %s" % self.url())
       except urllib2.URLError, v:
           raise PackageError("URL Error: %s " % self.url())
       except Exception, e:
           raise PackageError('Generic error: %s' % e)
       return html

    def _fetch_links(self, html):
        try:
            soup = BeautifulSoup(html)
        except HTMLParser.HTMLParseError, e:
            raise PackageError("HTML parse error: %s" % e)
        links = []
        for link in soup.findAll("a"):
            href = link.get("href")
            if href:
                links.append(href)
        return links

    def _links_external(self, html, filename_matches=None, follow_external_index_pages=False):
        """ pypi has external "download_url"s. We try to get anything
            from there too. This is really ugly and I'm not sure if there's
            a sane way.  The download_url directs either to a website which
            contains many download links or directly to a package.
        """

        #print "in _links_external"
        download_links = set()
        soup = BeautifulSoup(html)
        links = soup.findAll("a")
        for link in links:
            if link.renderContents().endswith("download_url"):
                # we have a download_url!! Yeah.
                url = link.get("href")
                if not url:
                    continue
                download_links.add(url)

            if link.renderContents().endswith("home_page"):
                # we have a download_url!! Yeah.
                url = link.get("href")
                if not url:
                    continue
                download_links.add(url)

        for link in download_links:
            # check if the link points directly to a file
            # and get it if it matches filename_matches
            if filename_matches:
                if self.matches(link, filename_matches):
                    yield link
                    continue

                # fetch what is behind the link and see if it's html.
                # If it is html, download anything from there.
                # This is extremely unreliable and therefore commented out.

                if follow_external_index_pages:
                    try:
                        r = requests.get(link)
                        #site = urlopen()
                    except Exception, e:
                        LOG.warn('Error downloading %s (%s)' % (link, e))
                        continue

                    if "text/html" not in r.headers['content-type']: 
                        continue

                    # we have a valid html page now. Parse links and download them.
                    # They have mostly no md5 hash.
                    html = r.content
                    real_download_links = self._fetch_links(html)
                    candidates = list()
                    for real_download_link in real_download_links:
                        # build absolute links

                        real_download_link = urllib.basejoin(r.url, real_download_link)
                        if not filename_matches or self.matches(real_download_link, filename_matches):

                            # we're not interested in dev packages
                            if not dev_package_regex.search(real_download_link):

                                # Consider only download links that starts with
                                # the current package name
                                filename = urlparse.urlsplit(real_download_link)[2].split('/')[-1]
                                if not filename.startswith(self.name):
                                    continue

                                candidates.append(real_download_link)

                    def sort_candidates(url1, url2):
                        """ Sort all download links by package version """
                        parts1 = urlparse.urlsplit(url1)[2].split('/')[-1]
                        parts2 = urlparse.urlsplit(url2)[2].split('/')[-1]
                        return cmp(pkg_resources.parse_version(parts1), pkg_resources.parse_version(parts2))

                    # sort the files
                    candidates.sort(sort_candidates)
                    
                    #print len(candidates)
                    #print candidates
                    
                    for c in candidates[-20:][::-1]:
                        yield c


    def _links(self, filename_matches=None, external_links=False, follow_external_index_pages=False):
        """ This is an iterator which returns useful links on files for
            mirroring
        """
        #print "in _links"
        remote_index_html = self._fetch_index()
        for link in self._fetch_links(remote_index_html):
            # then handle "normal" packages in pypi.
            (url, hash) = urllib.splittag(link)
            if not hash:
                continue
            try:
                (hashname, hash) = hash.split("=")
            except ValueError:
                continue
            if not hashname == "md5":
                continue

            if filename_matches:
                if not self.matches(url, filename_matches):
                    continue

            yield (url, hash)

        if external_links:
            for link in self._links_external(remote_index_html, filename_matches, follow_external_index_pages):
                yield (link, None)

    def matches(self, filename, filename_matches):
        #print "in matches"
        for filename_match in filename_matches:
            if fnmatch.fnmatch(filename, filename_match):
                return True

        # perhaps 'filename' is part of a query string, so 
        # try a regex match 
        for filename_match in filename_matches:
            regex = re.compile(r'\\%s\?' % filename_match)
            if regex.search(filename):
                return True
        
        return False

    def ls(self, filename_matches=None, external_links=False, follow_external_index_pages=True):
        #print "in _ls"
        links = self._links(filename_matches=filename_matches, 
                            external_links=external_links, 
                            follow_external_index_pages=follow_external_index_pages)
        #print "out of ls"
        return [(link[0], os.path.basename(link[0]), link[1]) for link in links]

    def _get(self, url, filename, md5_hex=None):
      """ fetches a file and checks for the md5_hex if given
      """
      # since some time in Feb 2009 PyPI uses different and relative URLs
      if url.startswith('../../packages'):
         url = 'https://pypi.python.org/' + url[6:]
         #print "url is --> ", url
         #print "filename is -->", filename
      try:
         r = requests.get(url)
         if 'text/html' in r.headers['content-type']:
             raise PackageError("File no longer exists. HTML returned rather than package.")
         data = r.content
      except Exception as e:
         raise PackageError("Couldn't download (%s): %s" % (e, url))
      if md5_hex:
         # check for md5 checksum
         data_md5 = md5(data).hexdigest()
         if md5_hex != data_md5:
            raise PackageError("MD5 sum does not match: %s / %s on package %s" % (md5_hex, data_md5, url))
      return data
      
    def get(self, link):
        """ link is a tuple of url, md5_hex
        """
        #print "in get"
        return self._get(*link)

    def content_length(self, link):

        # First try to determine the content-length through
        # HEAD request in order to save bandwidth

        #print "in content_length"
        try:
            r = requests.head(link)
            ct = r.headers['content-length']
            if ct is not None:
                ct = long(ct)
                return ct
        except Exception, e:
            LOG.warn('Could not obtain content-length through a HEAD request from %s (%s)' % (link, e))

        return 0

class Mirror(object):
    """ This represents the whole mirror directory
    """
    def __init__(self, base_path):
        self.base_path = base_path
        self.mkdir()

    def mkdir(self):
        try:
            os.mkdir(self.base_path)
        except OSError:
            # like "File exists"
            pass

    def package(self, package_name):
        return MirrorPackage(self, package_name)

    def cleanup(self, remote_list, verbose=False):
        return

    def rmr(self, path):
        return

    def ls(self):
        filenames = []
        for filename in os.listdir(self.base_path):
            if os.path.isdir(os.path.join(self.base_path, filename)):
                filenames.append(filename)
        filenames.sort()
        return filenames

    def _html_link(self, filename):
        return '<a href="%s/">%s</a>' % (filename, filename)

    def _index_html(self):
        header = "<html><head><title>PyPI Mirror</title></head><body>"
        header += "<h1>PyPI Mirror</h1><h2>Last update: " + \
                  datetime.datetime.utcnow().strftime("%c UTC")+"</h2>\n"
        _ls = self.ls()
        links = "<br />\n".join([self._html_link(link) for link in _ls])
        generator = "<p class='footer'>Generated by %s; %d packages mirrored. For details see the <a href='http://www.coactivate.org/projects/pypi-mirroring'>z3c.pypimirror project page.</a></p>" % (pypimirror_version(), len(_ls))
        footer = "</body></html>\n"
        return "\n".join((header, links, generator, footer))

    def index_html(self):
        content = self._index_html()
        open(os.path.join(self.base_path, "index.html"), "wb").write(content)

    def full_html(self, full_list):
        header = "<html><head><title>PyPI Mirror</title></head><body>"  
        header += "<h1>PyPi Mirror</h1><h2>Last update: " + \
                  time.strftime("%c %Z")+"</h2>\n"
        footer = "</body></html>\n"
        fp = file(os.path.join(self.base_path, "full.html"), "wb")
        fp.write(header)
        fp.write("<br />\n".join(full_list))
        fp.write(footer)
        fp.close()

    def mirror(self, 
               package_list, 
               filename_matches, 
               verbose, 
               cleanup, 
               create_indexes, 
               external_links, 
               follow_external_index_pages, 
               base_url):

        cur_pkg_counter = 0
        filename = None
        
        pkg_ctr_filename = "pkg_ctr.txt"        
        if os.path.isfile(pkg_ctr_filename):
            cur_pkg_counter = int(open(pkg_ctr_filename, "r").readline()) 
            package_list = package_list[cur_pkg_counter-1:]
        
        total_pkg_count = len(package_list)+cur_pkg_counter
        stats = Stats()
        full_list = []
        for package_name in package_list:

            cur_pkg_counter += 1
            LOG.debug('Processing package %s (%s of %s)' % (package_name, str(cur_pkg_counter), str(total_pkg_count)))

            try:
                package = Package(package_name)
            except PackageError, v:
                stats.error_invalid_package(package_name)
                LOG.debug("Package is not valid.")
                continue

            try:
                links = package.ls(filename_matches, external_links, 
                                   follow_external_index_pages)
            except PackageError, v:
                stats.error_404(package_name)
                LOG.debug("Package " + package_name + " not available: %s" % v)
                continue

            mirror_package = self.package(package_name)

            for (url, url_basename, md5_hash) in links:
                #if url.find('prdownloads.sourceforge.net') > -1 and url.find('?download') > -1:
                #   url = url.split('?')[0]
                #   url_basename = url_basename.split('?')[0]
                try:
                   url, filename = self._extract_filename(url)
                except PackageError, v:
                   stats.error_invalid_url((url, url_basename, md5_hash))
                   LOG.info("Invalid URL: " + url + " %s" % v)
                   continue                                
                 

                if url != None and filename != None:
                  # LOG.debug ("--> " + url + " [" + filename + "]")
                  # if we have a md5 check hash and continue if fine.
                  
                  if (md5_hash and mirror_package.md5_match(url_basename, md5_hash)) or \
                     os.path.exists(os.path.join(local_pypi_path, package_name, filename)):
                      stats.found(filename)
                      full_list.append(mirror_package._html_link(base_url, 
                                                                 url_basename, 
                                                                 md5_hash))
                      if verbose: 
                          LOG.debug("  Found: %s" % filename)
                      continue
                  
                  # if we don't have a md5, check for the filesize, if available
                  # and continue if it's the same:
                  if not md5_hash:
                      remote_size = package.content_length(url)
                      if mirror_package.size_match(url_basename, remote_size):
                          if verbose: 
                              LOG.debug("  Found: %s" % url_basename)
                          full_list.append(mirror_package._html_link(base_url, url_basename, md5_hash))
                          continue
                
                  # we need to download it
                  #while True:
                  try:
                      LOG.debug("Attempting Download: %s" % url)
                      data = package.get((url, filename, md5_hash))
                  except PackageError, v:
                      stats.error_invalid_url((url, url_basename, md5_hash))
                      LOG.info("Invalid URL: " + url + " %s" % v)
                      continue
                                        
                  mirror_package.write(filename, data, md5_hash)
                  stats.stored(filename)
                  # base_url
                  # url_basename
                  full_list.append(mirror_package._html_link(base_url, filename, md5_hash))
                  if verbose:
                      LOG.debug("  Stored File  : %s [%d kB]" % (filename, len(data)//1024))
                  
                  fullpath_filename = os.path.join(local_pypi_path, package_name, filename)
                  LOG.debug ("  Touching archive: " + fullpath_filename)    
                  touch_archives.process_file(fullpath_filename, False)
            open(pkg_ctr_filename, "w").write(str(cur_pkg_counter-1))

# Disabled cleanup for now since it does not deal with the changelog() implementation
#            if cleanup:
#                mirror_package.cleanup(links, verbose)
            if create_indexes and filename != None:
                mirror_package.index_html(base_url)
#        if cleanup:
#            self.cleanup(package_list, verbose)

        # The pass has completed successfully so delete the temporary
        # counter and the pickled package-list files 
        if os.path.isfile(pkg_ctr_filename):
           os.remove(pkg_ctr_filename)
        if os.path.isfile("packages.p"):
           os.remove("packages.p")
        if os.path.isfile("incremental_packages.p"):
           os.remove("incremental_packages.p")
        
        # Generate the local HTML pages
        if create_indexes and filename != None:
            self.index_html()
            full_list.sort()
            self.full_html(full_list)

        for line in stats.getStats():
            LOG.debug(line)

    def _extract_filename(self, url):
        """Get the real filename from an arbitary pypi download url.      
        We need to use heuristics here to avoid a many HEAD
        requests. Use them only if heuristics is not possible. 
        """
        fetch_url = url
        #old_fetch_url = ""
        extract_counter = 0
        do_again = True
        while do_again:
            # heuristics start
            url_basename = os.path.basename(fetch_url)                
            # do we have GET parameters? 
            # if not, we believe the basename is the filename
            
            # Workaround for "Old File" encountered error
            if fetch_url.find('downloads.sourceforge.net') > 0 and fetch_url.find('project') > 0:
               fetch_url = fetch_url.replace('downloads.sourceforge.net', 'garr.dl.sourceforge.net')
               fetch_url = fetch_url.replace('?download=', '')
               url_basename = os.path.basename(fetch_url)
               LOG.debug("Fetch URL is " + fetch_url)
               
            if '?' not in url_basename:
                return [fetch_url, os.path.basename(fetch_url)]

            if extract_counter > 15:
                return [None, None]
            # now we have get parameters, we need to do a head 
            # request to get the filename
            extract_counter += 1
            try:
                LOG.debug("Head-Request to get filename for %s" % fetch_url)
                parsed_url = urlparse.urlparse(fetch_url)
                if parsed_url.scheme == 'https':
                    port = parsed_url.port or 443
                    conn = httplib.HTTPSConnection(parsed_url.netloc, port)
                else:
                    port = parsed_url.port or 80
                    conn = httplib.HTTPConnection(parsed_url.netloc, port)
                conn.request('HEAD', fetch_url)
                resp = conn.getresponse()
                #print "Location " + resp.getheader("Location", None)
                if resp.status in (301, 302):
                    fetch_url = resp.getheader("Location", None)
                    if fetch_url.find('sourceforge.net') > -1 and fetch_url.find('/OldFiles/') > -1:
                       LOG.debug("SourceForge 'Old File' (Invalid Redirect)")
                       return [None, None]
                       
                    #print "Location " + resp.getheader("Location", None)
                    if fetch_url is not None:
                        continue
                    raise PackageError, "Redirect (%s) from %s without location" % \
                                        (resp.status, fetch_url)
                elif resp.status != 200:                
                    raise PackageError, "URL %s can't be fetched" % fetch_url
                do_again = False
            except:
                pass  
        content_disposition = resp.getheader("Content-Disposition", None)
        if content_disposition:
            content_disposition = [_.strip() for _ in \
                                   content_disposition.split(';') \
                                   if _.strip().startswith('filename')]
            if len(content_disposition) == 1 and '=' in content_disposition[0]:
                return [fetch_url, content_disposition[0].split('=')[1].strip('"')]
        # so we followed redirects and no meaningful name came back, last 
        # fallback is to use the basename w/o request parameters.
        # if this is wrong, it has to fail later. 
        return [fetch_url, os.path.basename(fetch_url[:fetch_url.find('?')])]

class MirrorPackage(object):
    """ This checks for already existing files and creates the index
    """
    def __init__(self, mirror, package_name):
        self.package_name = package_name
        self.mirror = mirror
        self.mkdir()

    def mkdir(self):
        try:
            os.mkdir(self.path())
        except OSError:
            # like "File exists"
            pass

    def path(self, filename=None):
        if not filename:
            return os.path.join(self.mirror.base_path, self.package_name)
        return os.path.join(self.mirror.base_path, self.package_name, filename)

    def md5_match(self, filename, md5):
        file = MirrorFile(self, filename)
        return file.md5 == md5

    def size_match(self, filename, size):
        file = MirrorFile(self, filename)
        return file.size == size

    def write(self, filename, data, hash=""):
        self.mkdir()
        file = MirrorFile(self, filename)
        file.write(data)
        if hash:
            file.write_md5(hash)

    def rm(self, filename):
        MirrorFile(self, filename).rm()

    def ls(self):
        filenames = []
        for filename in os.listdir(self.path()):
            if os.path.isfile(self.path(filename)) and filename != "index.html"\
               and not filename.endswith(".md5"):
                filenames.append(filename)
        filenames.sort()
        return filenames

    def _html_link(self, base_url, filename, md5_hash):
        base_url = ''
        return '<a href="%s">%s</a>' % (filename, filename)

    def _index_html(self, base_url):
        header = "<html><head><title>%s &ndash; PyPI Mirror</title></head><body>" % self.package_name
        footer = "</body></html>"

        link_list = []
        for link in self.ls():
            file = MirrorFile(self, link)
            md5_hash = file.md5
            link_list.append(self._html_link(base_url, link, md5_hash))
        links = "<br />\n".join(link_list)
        divr = "<hr><center><a href=info.html>Info<hr></a></center>"
        return "%s%s%s%s" % (header, divr, links, footer)

    def index_html(self, base_url):
        content = self._index_html(base_url)
        self.write("index.html", content)

    def cleanup(self, original_file_list, verbose=False):
        return
        #remote_list = [link[1] for link in original_file_list]
        #local_list = self.ls()
        #for local_file in local_list:
        #    if not local_file.endswith(".md5") and \
        #            local_file not in remote_list:
        #        if verbose: 
        #            LOG.debug("Removing: %s" % local_file)
        #        self.rm(local_file)


class MirrorFile(object):
    """ This represents a mirrored file. It doesn't have to
        exist.
    """
    def __init__(self, mirror_package, filename):
        self.path = mirror_package.path(filename)


    @property
    def md5(self):
        # use cached md5 sum if available.
        if os.path.exists(self.md5_filename):
            return open(self.md5_filename,"r").read()

        if os.path.exists(self.path):
            return md5(open(self.path, "rb").read()).hexdigest()
        return None

    @property
    def size(self):
        if os.path.exists(self.path):
            return os.path.getsize(self.path)
        return 0

    def write(self, data):
        open(self.path, "wb").write(data)
        

    def rm(self):
        """ deletes the file
        """
        if os.path.exists(self.path):
            os.unlink(self.path)
        if os.path.exists(self.md5_filename):
            os.unlink(self.md5_filename)

    def write_md5(self, hash):
        md5_filename = ".%s.md5" % os.path.basename(self.path)
        md5_path = os.path.dirname(self.path)
        open(os.path.join(md5_path, md5_filename),"w").write(hash)

    @property
    def md5_filename(self):
        md5_filename = ".%s.md5" % os.path.basename(self.path)
        md5_path = os.path.dirname(self.path)
        return os.path.join(md5_path, md5_filename)

################# Config file parser

default_logfile = os.path.join(tempfile.tempdir or '/tmp', 'pypimirror.log')

config_defaults = {
    'base_url': 'http://your-host.com/index/',
    'mirror_file_path': '/tmp/mirror',
    'lock_file_name': 'pypi-poll-access.lock',
    'filename_matches': '*.zip *.tgz *.egg *.tar.gz *.tar.bz2 *.whl *.py *.md *.md5 *.xml *.sha1', # may be "" for *
    'package_matches': "", # "zope.app.* plone.app.*", # may be "" for *
    'cleanup': False, # delete local copies that are remotely not available
    'create_indexes': True, # create index.html files
    'verbose': True, # log output
    'log_filename': default_logfile,
    'external_links': True, # experimental external link resolve and download
    'follow_external_index_pages' : True, # experimental, scan index pages for links
}


# ATT: fix the configuration behaviour (with non-existing configuration files,
# etc.)

def get_config_options(config_filename):
    """
    Get options from the DEFAULT section of our config file
    
    @param dest
    Directory configuration file

    @return
    dict containing a key per option
    values are not reformatted - especially multiline options contain
    newlines
    this contains at least the following key/values:
    - include - Glob-Patterns for package names to include
    - suffixes - list of suffixes to mirror
    """
    if not os.path.exists(config_filename):
        return config_defaults

    config = ConfigParser.ConfigParser(config_defaults)
    config.read(config_filename)
    return config.defaults()


def run(args=None):
   
    global LOG
    global local_pypi_path
    
    usage = "usage: pypimirror [options] <config-file>"
    parser = optparse.OptionParser(usage=usage)
    parser.add_option('-v', '--verbose', dest='verbose', action='store_true',
                      default=True, help='verbose on')
    parser.add_option('-f', '--log-filename', dest='log_filename', action='store',
                      default=False, help='Name of logfile')
    parser.add_option('-I', '--initial-fetch', dest='initial_fetch', action='store_true',
                      default=False, help='Initial PyPI mirror fetch')
    parser.add_option('-U', '--update-fetch', dest='update_fetch', action='store_true',
                      default=False, help='Perform incremental update of the mirror')
    parser.add_option('-c', '--log-console', dest='log_console', action='store_true',
                      default=True, help='Also log to console')
    parser.add_option('-i', '--indexes-only', dest='indexes_only', action='store_true',
                      default=False, help='create indexes only (no mirroring)')
    parser.add_option('-e', '--follow-external-links', dest='external_links', action='store_true',
                      default=True, help='Follow and download external links)')
    parser.add_option('-x', '--follow-external-index-pages', dest='follow_external_index_pages', action='store_true',
                      default=False, help='Follow external index pages and scan for links')
    parser.add_option('-d', '--fetch-since-days', dest='fetch_since_days', action='store',
                      default=7, help='Days in past to fetch for incremental update')
    parser.add_option('-H', '--fetch-since-hours', dest='fetch_since_hours', action='store',
                      default=0, help='Hours in past to fetch for incremental update')
    parser.add_option('-a', '--autocalc', dest='autocalc', action='store_true',
                      default=False, help='Automatically calc how many hours since last run and fetch based on that time')
    parser.add_option('-n', '--nonstop', dest='nonstop', action='store_true',
                      default=False, help='nonstop loop')
    parser.add_option('-r', '--restart', dest='restart', action='store_true',
                      default=False, help='restart with clean indexes')
    options, args = parser.parse_args()
    if len(args) != 1:
        parser.error("No configuration file specified")
        sys.exit(1)
    
    config_file_name = os.path.abspath(args[0])
    config = get_config_options(config_file_name)

    local_pypi_path = config["mirror_file_path"]
       
    # correct things from config
    nonstop = options.nonstop
    filename_matches = config["filename_matches"].split()
    package_matches = config["package_matches"].split()
    cleanup = config["cleanup"] in ("True", "1")
    create_indexes = config["create_indexes"] in ("True", "1")
    verbose = config["verbose"] in ("True", "1") or options.verbose
    external_links = config["external_links"] in ("True", "1") or options.external_links
    follow_external_index_pages = config["follow_external_index_pages"] in ("True", "1") or options.follow_external_index_pages
    log_filename = config['log_filename']
    
    if options.autocalc:
       seconds_past = time.time() - os.path.getmtime(log_filename)
       hours_past = seconds_past / 3600
       if hours_past > 0:
         options.fetch_since_hours = hours_past + 3
    
    if int(options.fetch_since_days) > 0:
       fetch_since_days = int(options.fetch_since_days)
    else:
       fetch_since_days = int(config.get("fetch_since_days", 0) or options.fetch_since_days)
    
    fetch_since_hours = int(options.fetch_since_hours)   
    
    if options.log_filename:
        log_filename = options.log_filename

    LOG = getLogger(filename=log_filename, log_console=options.log_console)


    if options.restart:
        print time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()) + (" " * 12) + "Erasing old package data and restarting"
        if os.path.isfile("pkg_ctr.txt"):
           os.remove("pkg_ctr.txt")
        if os.path.isfile("packages.p"):
           os.remove("packages.p")
        if os.path.isfile("incremental_packages.p"):
           os.remove("incremental_packages.p")
      

    if options.initial_fetch:
        package_list = PypiPackageList().list(package_matches, incremental=False)
    elif options.update_fetch:
        if fetch_since_hours > 0:
           package_list = PypiPackageList().list(package_matches, incremental=True, fetch_since_days=0, fetch_since_hours=fetch_since_hours)
        else: 
           package_list = PypiPackageList().list(package_matches, incremental=True, fetch_since_days=fetch_since_days)
        
    else: 
        raise ValueError('You must either specify the --initial-fetch or --update-fetch option ')

    mirror = Mirror(config["mirror_file_path"])
    
    lock = zc.lockfile.LockFile(os.path.join(config["mirror_file_path"], config["lock_file_name"]))
    

    try:
        if options.indexes_only:
            mirror.index_html()
        else:
            while True:
                try:
                    mirror.mirror(package_list, filename_matches, verbose, 
                                  cleanup, create_indexes, external_links, 
                                  follow_external_index_pages, config["base_url"])
                except Exception as e:
                   LOG.debug(GetExceptionInfo())
                   print GetExceptionInfo()
                if not nonstop:
                   break
                else:
                   LOG.debug('Pausing ' + (str(fetch_since_hours) + ' hours ' if fetch_since_hours > 0 else '23 hours ') + 'for repeat... ')
                   if fetch_since_hours > 0:
                       time.sleep(3600 * fetch_since_hours) # 60 secs * 60 minutes = 1 Hour * Number of Hours to Pause
                       package_list = PypiPackageList().list(package_matches, incremental=True, fetch_since_hours=fetch_since_hours)
                   else:
                       time.sleep(3600 * 23)
                       package_list = PypiPackageList().list(package_matches, incremental=True, fetch_since_days=1)
    except:
       LOG.debug(GetExceptionInfo())

if __name__ == '__main__':
    sys.exit(run())

