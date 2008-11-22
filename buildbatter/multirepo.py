from buildbot.changes import svnpoller
from buildbot.changes.changes import Change
from buildbot.scheduler import Scheduler
from buildbot.steps import source
from twisted.web import html


def custom_get_HTML_box(self, url):
    """
    A custom version of Change.get_HTML_box that includes the repository
    name.
    """
    who = self.getShortAuthor()

    if hasattr(self, "repo_name"):
        repo_desc = " (%s)" % self.repo_name
    else:
        repo_desc = ""

    return '<a href="%s" title="%s">%s%s</a>' % (url,
                                                 html.escape(self.comments),
                                                 html.escape(who),
                                                 html.escape(repo_desc))

Change.get_HTML_box = custom_get_HTML_box


class SVNPoller(svnpoller.SVNPoller):
    """
    Polls an SVN repository, attaching a repository name for filtering
    purposes.
    """
    def __init__(self, repo_name, svnurl, *args, **kwargs):
        svnpoller.SVNPoller.__init__(self, svnurl, *args, **kwargs)
        self.repo_name = repo_name

    def create_changes(self, new_logentries):
        changes = svnpoller.SVNPoller.create_changes(self, new_logentries)

        for change in changes:
            change.repo_name = self.repo_name

        return changes


class RepoChangeScheduler(Scheduler):
    """
    A scheduler that only triggers a build if the repository name of the
    change matches the name configured with the scheduler.
    """
    def __init__(self, repo_names, *args, **kwargs):
        Scheduler.__init__(self, *args, **kwargs)
        self.repo_names = repo_names

    def addChange(self, change):
        if (not hasattr(change, "repo_name") or
            change.repo_name in self.repo_names):
            return Scheduler.addChange(self, change)


class SVN(source.SVN):
    """
    An SVN source that ties changes directory with the configured repository
    name for use with RepoChangeScheduler and our SVNPoller.
    """
    def __init__(self, reponame, allow_patch=True, *args, **kwargs):
        source.SVN.__init__(self, *args, **kwargs)
        self.reponame = reponame
        self.allow_patch = allow_patch

    def describe(self, done=False):
        s = source.SVN.describe(self, done)
        s.insert(1, self.reponame)
        return s

    def start(self):
        s = self.build.getSourceStamp()
        backup_patch = s.patch
        backup_revision = s.revision
        backup_alwaysUseLatest = self.alwaysUseLatest

        if s.patch:
            if self.allow_patch:
                self.alwaysUseLatest = False
            else:
                s.patch = None
                s.revision = None

        source.SVN.start(self)

        s.patch = backup_patch
        s.revision = backup_revision
        self.alwaysUseLatest = backup_alwaysUseLatest
