from buildbot.process import factory
from buildbot.process.properties import WithProperties
from buildbot.scheduler import Try_Jobdir, Triggerable, Nightly
from buildbot.steps.shell import ShellCommand, Test, SetProperty
from buildbot.steps.trigger import Trigger

from multirepo import RepoChangeScheduler, SVN, SVNPoller
from steps import BuildEgg, BuildSDist, LocalCommand, VirtualEnv, EasyInstall


def get_builder_name(target_name, combination, pyver, branch, sandbox=False):
    if target_name == combination[0]:
        if branch and branch.name != combination[1]:
            return None

        suffix = ""
    else:
        suffix = "%s_%s_" % (combination[0], combination[1])

    if sandbox:
        suffix += "sandbox_"


    if branch and branch.name != "trunk":
        name = target_name + "_" + branch.name
    else:
        name = target_name

    return "%s_%spy%s" % (name, suffix, pyver)


def get_trigger_name(target_name, combination, pyver, branch):
    suffix = "%s_%s_" % (combination[0], combination[1])
    return "triggered_%s_%spy%s" % (target_name, suffix, pyver)


class BuildManager(object):
    """
    Manages several BuildTarget and BuildDependency instances, setting up
    polling, dependencies, and slaves.
    """
    def __init__(self, slave_info, combinations, pyvers=["2.4", "2.5"]):
        self.targets = {}
        self.target_list = []
        self.pyvers = pyvers
        self.slave_info = slave_info
        self.combinations = combinations

    def add(self, targets):
        self.target_list = targets

        for target in targets:
            self.targets[target.name] = target
            target.manager = self

    def get_pollers(self):
        pollers = []

        for target in self.target_list:
            pollers.extend(target.get_pollers())

        return pollers

    def get_schedulers(self):
        schedulers = []

        for target in self.target_list:
            schedulers.extend(target.get_nightly_schedulers())

        for target in self.target_list:
            schedulers.extend(target.get_schedulers())

        for target in self.target_list:
            schedulers.extend(target.get_sandbox_schedulers())

        return schedulers

    def get_builders(self):
        builders = []
        sandbox_builders = []

        rev_target_list = self.target_list
        rev_target_list.reverse()

        for target in rev_target_list:
            for combination in self.combinations:
                for pyver in self.pyvers:
                    python = "python%s" % pyver
                    env={}

                    builders.extend(
                        target.get_builders(combination, python, pyver, env))
                    sandbox_builders.extend(
                        target.get_sandbox_builders(combination, python,
                                                    pyver, env))

        return builders + sandbox_builders


class Branch(object):
    """
    Information on a branch. This is in charge of setting up any pollers
    needed. Right now, this is pretty limited to multirepo.SVNPoller.
    """
    def __init__(self, name, url, poll_class=SVNPoller, poll_frequency=60*20):
        self.name = name
        self.url = url
        self.poll_class = poll_class
        self.poll_frequency = poll_frequency
        self.target = None

    def get_poller(self):
        if self.poll_frequency == 0:
            return None

        return self.poll_class(self.name, self.url, self.poll_frequency)

    def add_checkout_step(self, f, workdir):
        f.addStep(SVN, reponame=self.target.name,
                  svnurl=self.url,
                  mode="update",
                  alwaysUseLatest=True,
                  workdir=workdir)


class BuildTarget(object):
    def __init__(self, name, branches, build_rules=None, dependencies=[],
                 allow_sandbox=False, nightly=False, triggers=[],
                 wait_for_triggers=False, trigger_properties={}):
        self.manager = None
        self.name = name
        self.branches = branches
        self.dependencies = dependencies
        self.allow_sandbox = allow_sandbox
        self.triggers = triggers
        self.wait_for_triggers = wait_for_triggers
        self.trigger_properties = trigger_properties
        self.build_rules = build_rules
        self.nightly = nightly

        for branch in self.branches:
            branch.target = self

    def get_pollers(self):
        pollers = []

        for branch in self.branches:
            poller = branch.get_poller()

            if poller is not None:
                pollers.append(poller)

        return pollers

    def get_schedulers(self):
        if not self.build_rules or self.nightly:
            return []

        schedulers = []
        builderNames = []

        for pyver in self.manager.pyvers:
            for combination in self.manager.combinations:
                for branch in self.branches:
                    name = get_builder_name(self.name, combination,
                                            pyver, branch)

                    if name:
                        builderNames.append(name)

                        schedulers.append(Triggerable(
                            name=get_trigger_name(self.name, combination,
                                                  pyver, branch),
                            builderNames=[name]
                        ))

        schedulers.append(RepoChangeScheduler(
            name=self.name,
            repo_names=[self.name],
            branch=None, treeStableTimer=60,
            builderNames=builderNames,
        ))

        return schedulers

    def get_nightly_schedulers(self):
        if not self.nightly:
            return []

        builderNames = []

        for pyver in self.manager.pyvers:
            for combination in self.manager.combinations:
                for branch in self.branches:
                    builderNames.append(
                        get_builder_name(self.name, combination, pyver, branch))

        return [Nightly(
            name=self.name,
            branch=None,
            builderNames=builderNames,
            hour=0,
            minute=0
        )]

    def get_sandbox_schedulers(self):
        if self.allow_sandbox:
            builder_names = []

            for pyver in self.manager.pyvers:
                for combination in self.manager.combinations:
                    for branch in self.branches:
                        name = get_builder_name(self.name, combination,
                                                pyver, branch, True)

                        if name:
                            builder_names.append(name)

            return [Try_Jobdir(
                name="sandbox_%s" % self.name,
                builderNames=builder_names,
                jobdir="jobdir_%s" % self.name)]

        return []

    def get_builders(self, combination, python, pyver, env, category="builds",
                     sandbox=False):
        if self.build_rules is None:
            return []

        builders = []

        for branch in self.branches:
            if pyver not in self.manager.slave_info:
                continue

            name = get_builder_name(self.name, combination, pyver,
                                    branch, sandbox)

            if not name:
                continue

            workdir = self.name
            slavename = self.manager.slave_info[pyver][0]

            f = factory.BuildFactory()
            self.build_rules.setup(self, branch, python, pyver, workdir, env,
                                   combination, sandbox)
            self.build_rules.addSteps(f)

            builders.append({
                'name': name,
                'slavename': slavename,
                'builddir': name,
                'factory': f,
                'category': category,
            })

        return builders

    def get_sandbox_builders(self, combination, python, pyver, env):
        if self.allow_sandbox:
            return self.get_builders(combination, python, pyver, env,
                                     "sandbox", True)

        return []


class BuildDependency(object):
    pass


class BuildRules(object):
    def __init__(self):
        pass

    def setup(self, target, branch, python, pyver, workdir,
              env, combination, sandbox):
        self.target = target
        self.branch = branch
        self.python = python
        self.pyver = pyver
        self.workdir = workdir
        self.env = env
        self.combination = combination
        self.sandbox = sandbox

    def addSteps(self, f):
        self.addCheckoutSteps(f)

        nightly = WithProperties("%(nightly:-" +
                                 str(self.target.nightly) +
                                 ")s")

        self.addTestSteps(f)
        self.addBuildSteps(f)
        self.addUploadSteps(f)

        for trigger in self.target.triggers:
            f.addStep(CustomTrigger,
                      schedulerNames=[
                          get_trigger_name(trigger, self.combination,
                                           self.pyver, self.branch),
                      ],
                      waitForFinish=self.target.wait_for_triggers or nightly,
                      updateSourceStamp=False,
                      set_properties=dict({
                          "nightly": nightly,
                          "upload_path": WithProperties("%(upload_path:-)s")
                      }, **self.target.trigger_properties))

    def addCheckoutSteps(self, f):
        if self.branch:
            self.branch.add_checkout_step(f, self.workdir)

    def addTestSteps(self, f):
        pass

    def addBuildSteps(self, f):
        pass

    def addUploadSteps(self, f):
        pass


class PythonModuleBuildRules(BuildRules):
    def __init__(self, upload_path=None, upload_url=None,
                 build_eggs=True, egg_deps=[], find_links=[],
                 *args, **kwargs):
        BuildRules.__init__(self, *args, **kwargs)
        self.upload_path = upload_path
        self.upload_url = upload_url
        self.build_eggs = build_eggs
        self.egg_deps = egg_deps
        self.find_links = find_links

    def addSteps(self, f):
        f.addStep(VirtualEnv, python=self.python)

        self.env["PATH"] = "bin:../build/bin:/bin:/usr/bin"
        self.env["PYTHONPATH"] = "lib/%(python)s" \
                                 ":../build/lib/%(python)s" \
                                 ":lib/%(python)s/site-packages" \
                                 ":../build/lib/%(python)s/site-packages" \
                                 % {
                                     "python": self.python
                                 }

        self.addEggSteps(f)
        BuildRules.addSteps(self, f)

    def addEggSteps(self, f):
        if self.egg_deps:
            f.addStep(EasyInstall,
                      packages=self.egg_deps,
                      find_links=[self.upload_url] + self.find_links,
                      env=self.env)

    def addBuildSteps(self, f):
        if self.combination == ("django", "trunk"):
            #f.addStep(ShellCommand,
            #          command=["rm", "-rf", "build", "dist"],
            #          description="removing build directory",
            #          descriptionDone="removed build directory",
            #          workdir=self.workdir)
            f.addStep(BuildSDist,
                      workdir=self.workdir,
                      use_egg_info=self.build_eggs,
                      env=self.env)

            if self.build_eggs:
                f.addStep(BuildEgg,
                          workdir=self.workdir,
                          env=self.env)


class CustomTrigger(Trigger):
    haltOnFailure = True

    def __init__(self, waitForFinish=False, *args, **kwargs):
        Trigger.__init__(self, waitForFinish=waitForFinish, *args, **kwargs)
        self.myWaitForFinish = waitForFinish

    def start(self):
        result = self.build.getProperties().render(self.myWaitForFinish)
        self.waitForFinish = (str(result) == "True")

        Trigger.start(self)

        self.waitForFinish = self.myWaitForFinish
