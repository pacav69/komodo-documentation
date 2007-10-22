
"""Tasks for checking things in the doc tree.

    mk check:*
"""

import os
from os.path import join, dirname, normpath, abspath, isabs, exists, \
                    splitext, basename
import re
import sys
from urlparse import urlparse
from pprint import pprint

from mklib import Task, Configuration, Alias
from mklib import sh
from mklib.common import MkError

try:
    from xml.etree import cElementTree as ET
except ImportError:
    try:
        import cElementTree as ET
    except ImportError:
        try:
            from elementtree import ElementTree as ET
        except ImportError:
            # Use our local limited pure-python ElementTree.
            etree_dir = join(dirname(dirname(abspath(__file__))),
                             "externals", "elementtree")
            sys.path.insert(0, etree_dir)
            from elementtree import ElementTree as ET
            sys.path.remove(etree_dir)

from buildsupport import paths_from_path_patterns, _KomodoDocTask



class cfg(Configuration):
    dir = ".."


class all(Alias):
    deps = ["links", "toc"]
    default = True

class links(_KomodoDocTask):
    """Check links in the built htdocs."""
    _doc_from_path = None # lazily built '_Document' instances for each path

    def doc_from_path(self, path):
        if self._doc_from_path is None:
            self._doc_from_path = {}
        if path not in self._doc_from_path:
            try:
                if basename(path) == "toc.xml":
                    self._doc_from_path[path] = _TOCDocument(path)
                else:
                    self._doc_from_path[path] = _Document(path)
            except SyntaxError, ex:
                # Currently only handle XHTML.
                print "%s: can't parse: %s" % (path, ex)
                self._doc_from_path[path] = None
        return self._doc_from_path[path]

    def src_path_from_htdocs_path(self, htdocs_path):
        assert htdocs_path.startswith(self.htdocs_dir)
        return join(self.cfg.lang, htdocs_path[len(self.htdocs_dir)+1:])

    def make(self):
        if not exists(self.htdocs_dir):
            raise MkError("`%s' does not exist: you need to run `mk htdocs` first"
                          % self.htdocs_dir)
        
        paths = [normpath(p) for p in paths_from_path_patterns(
                    [self.htdocs_dir],
                    includes=["*.html"],
                    excludes=[".svn", "*.pyc"])]
        self.linkcheck(paths)

    def _check_a_link(self, doc, href):
        self.log.debug("check `%s' link in %s", href, doc)
        scheme, netloc, path, params, query, fragment = urlparse(href)
        assert not scheme and not netloc, "can't yet check external links"
        assert not query, "don't know how to check link with a query string"
        assert not params, "don't know how to check link with a params"
        if not path:
            actual_path = doc.path
        elif not isabs(path):
            actual_path = normpath(join(dirname(doc.path), path))
        else:
            actual_path = path
        if not exists(actual_path):
            print "%s: `%s' link does not exist" \
                  % (self.src_path_from_htdocs_path(doc.path), path)
            return False
        if fragment:
            link_doc = self.doc_from_path(actual_path)
            if link_doc is None:
                # An error will already have been logged.
                return False
            if fragment not in link_doc.anchors:
                print "%s: `%s#%s' anchor does not exist" \
                      % (self.src_path_from_htdocs_path(doc.path),
                         self.src_path_from_htdocs_path(actual_path),
                         fragment)
                return False
        return True

    def _is_external_link(self, href):
        return urlparse(href)[0] and True or False

    def linkcheck(self, paths, check_external_links=False):
        for path in paths:
            self.log.debug("linkcheck `%s'", path)
            doc = self.doc_from_path(path)
            if doc is None:
                continue # error will already have been logged
            for href in doc.links:
                if self._is_external_link(href) and not check_external_links:
                    self.log.debug("skip external link: %r", href)
                    continue
                self._check_a_link(doc, href)


class toc(links):
    """Check the toc.xml for sanity."""
    def make(self):
        toc_xml = join(self.htdocs_dir, "toc.xml")
        self.linkcheck([toc_xml])

    def linkcheck(self, paths, check_external_links=False):
        for path in paths:
            self.log.debug("linkcheck `%s'", path)
            doc = self.doc_from_path(path)
            if doc is None:
                continue # error will already have been logged
            for href in doc.links:
                if self._is_external_link(href) and not check_external_links:
                    self.log.debug("skip external link: %r", href)
                    continue
                self._check_a_link(doc, href)



#---- internal support stuff

class _Document(object):
    """Wrapper for an HTML file to provide convenience info for link
    checking.
    """
    def __init__(self, path):
        self.path = path
        self._gather_links_and_anchors(path)

    def _gather_links_and_anchors(self, path):
        # Handle HTML entities as per:
        # http://trac.turbogears.org/ticket/242
        root = ET.fromstring(self.fixentities(open(path).read()))

        # Gather links and anchors.
        self.anchors = set()
        self.links = set()
        ns = re.match("^{(.*?)}\w+$", root.tag).group(1)
        body = root.find("{%s}body" % ns)
        for elem in body.getiterator():
            if elem.tag == '{%s}a' % ns:
                if elem.get("href"):
                    self.links.add(elem.get("href"))
                elif elem.get("id"):
                    self.anchors.add(elem.get("id"))
                elif elem.get("name"):
                    self.anchors.add(elem.get("name"))
                else:
                    log.warn("<a> without href, id or name: %s",
                             elem.attrib)
            elif elem.get("id"):
                self.anchors.add(elem.get("id"))

    def __repr__(self):
        return "<_Document '%s'>" % self.path

    def fixentities(self, html):
        # Replace HTML character entities with numerical references.
        # Note: this won't handle CDATA sections properly.
        import htmlentitydefs
        def repl(m): 
            entity = htmlentitydefs.entitydefs.get(m.group(1).lower())
            if not entity:
                return m.group(0)
            elif len(entity) == 1:
                if entity in "&<>'\"":
                    return m.group(0)
                return "&#%d;" % ord(entity)
            else:
                return entity
        return re.sub("&(\w+);?", repl, html)


class _TOCDocument(_Document):
    """Wrapper for a toc.xml to provide convenience info for link
    checking.
    """
    def __repr__(self):
        return "<_TOCDocument '%s'>" % self.path
    def _gather_links_and_anchors(self, path):
        root = ET.fromstring(open(path).read())

        # Gather links and anchors.
        self.anchors = set()
        self.links = set()
        for elem in root.getiterator():
            if elem.tag == 'node' and elem.get("link"):
                self.links.add(elem.get("link"))