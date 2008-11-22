from buildbot.buildslave import BuildSlave


def create_slave_list():
    """
    Creates a list of all configures slaves from a slaves.cfg file.
    """
    slaves = []
    info = {}

    fp = open("slaves.cfg", "r")

    for line in fp.xreadlines():
        line = line.rstrip("\n")

        if line.startswith("#") or line == "":
            continue

        name, pyver, password = line.split("\t", 3)

        slaves.append(BuildSlave(name, password))

        if pyver not in info:
            info[pyver] = []

        info[pyver].append(name)

    fp.close()

    return slaves, info
