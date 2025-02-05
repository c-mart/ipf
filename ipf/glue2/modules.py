
###############################################################################
#   Copyright 2013-2014 The University of Texas at Austin                     #
#                                                                             #
#   Licensed under the Apache License, Version 2.0 (the "License");           #
#   you may not use this file except in compliance with the License.          #
#   You may obtain a copy of the License at                                   #
#                                                                             #
#       http://www.apache.org/licenses/LICENSE-2.0                            #
#                                                                             #
#   Unless required by applicable law or agreed to in writing, software       #
#   distributed under the License is distributed on an "AS IS" BASIS,         #
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  #
#   See the License for the specific language governing permissions and       #
#   limitations under the License.                                            #
###############################################################################

import subprocess
import os
import re
import hashlib

from ipf.error import StepError
from ipf.urnprefix import IPF_URN_PREFIX
from . import application
from . import service
from .types import AppEnvState, ApplicationHandle

#######################################################################################################################


class LModApplicationsStep(application.ApplicationsStep):
    def __init__(self):
        application.ApplicationsStep.__init__(self)

        self._acceptParameter("exclude", "a comma-separated list of modules to ignore (default is to ignore none)",
                              False)

    def _run(self):
        try:
            self.exclude = self.params["exclude"].split(",")
        except KeyError:
            self.exclude = []

        apps = application.Applications(self.resource_name)

        module_paths = []
        try:
            paths = os.environ["MODULEPATH"]
            module_paths.extend(list(map(os.path.realpath, paths.split(":"))))
        except KeyError:
            raise StepError("didn't find environment variable MODULEPATH")

        apps = application.Applications(self.resource_name)
        for path in module_paths:
            try:
                packages = os.listdir(path)
            except OSError:
                continue
            for name in packages:
                if name.startswith("."):
                    continue
                if not os.path.isdir(os.path.join(path, name)):
                    # assume these are modules that just import other modules
                    continue
                for file_name in os.listdir(os.path.join(path, name)):
                    if file_name.startswith("."):
                        continue
                    if file_name.endswith("~"):
                        continue
                    if file_name.endswith(".lua"):
                        self._addModule(os.path.join(
                            path, name, file_name), name, file_name[:len(file_name)-4], apps)
                    else:
                        self._addModule(os.path.join(
                            path, name, file_name), name, file_name, apps)
        return apps

    def _addModule(self, path, name, version, apps):
        env = application.ApplicationEnvironment()
        env.AppName = name
        env.AppVersion = version
        publishflag = True

        try:
            file = open(path)
        except IOError as e:
            self.warning("%s" % e)
            return
        text = file.read()
        file.close()

        m = re.search("\"Description:([^\"]+)\"", text)
        if m is not None:
            env.Description = m.group(1).strip()
        else:
            self.debug("no description in "+path)
        m = re.search("\"URL:([^\"]+)\"", text)
        if m is not None:
            env.Repository = m.group(1).strip()
        else:
            self.debug("no URL in "+path)
        m = re.search("\"Category:([^\"]+)\"", text)
        if m is not None:
            env.Extension["Category"] = list(
                map(str.strip, m.group(1).split(",")))
        else:
            self.debug("no Category in "+path)
        m = re.search("\"Keywords:([^\"]+)\"", text)
        if m is not None:
            env.Extension["Keywords"] = list(
                map(str.strip, m.group(1).split(",")))
        else:
            self.debug("no Keywords in "+path)
        m = re.search("\"IPF_FLAGS:([^\"]+)\"", text)
        if m is not None:
            #Currently only supporting NOPUBLISH
            flagslist = list(
                map(str.strip, m.group(1).split(",")))
            if "NOPUBLISH" in flagslist:
                publishflag = False
                self.debug("NOPUBLISH set for "+path)

        handle = application.ApplicationHandle()
        handle.Type = ApplicationHandle.MODULE
        handle.Value = name+"/"+version

        if publishflag is True:
            apps.add(env, [handle])

#######################################################################################################################


class ModulesApplicationsStep(application.ApplicationsStep):
    def __init__(self):
        application.ApplicationsStep.__init__(self)

        self._acceptParameter("exclude", "a comma-separated list of modules to ignore (default is to ignore none)",
                              False)

    def _run(self):
        try:
            self.exclude = self.params["exclude"].split(",")
        except KeyError:
            self.exclude = []

        apps = application.Applications(self.resource_name)

        module_paths = []
        try:
            paths = os.environ["MODULEPATH"]
            module_paths.extend(list(map(os.path.realpath, paths.split(":"))))
        except KeyError:
            raise StepError("didn't find environment variable MODULEPATH")

        for path in module_paths:
            self._addPath(path, path, module_paths, apps)

        return apps

    def _addPath(self, path, module_path, module_paths, apps):
        try:
            file_names = os.listdir(path)
        except OSError:
            return
        for name in file_names:
            if os.path.join(path, name) in module_paths:
                # don't visit other module paths
                continue
            if os.path.isdir(os.path.join(path, name)):
                self._addPath(os.path.join(path, name),
                              module_path, module_paths, apps)
            else:
                self._addModule(os.path.join(path, name), module_path, apps)

    def _addModule(self, path, module_path, apps):
        if os.path.split(path)[1].startswith("."):
            return
        if path.endswith("~"):
            return

        # print(path)

        file = open(path)
        lines = file.readlines()
        file.close()

        if len(lines) == 0 or not lines[0].startswith("#%Module"):
            return

        env = application.ApplicationEnvironment()

        str = path[len(module_path)+1:]
        slash_pos = str.find("/")  # assumes Unix-style paths
        if slash_pos == -1:
            env.AppName = str
            env.AppVersion = None
        else:
            env.AppName = str[:slash_pos]
            env.AppVersion = str[slash_pos+1:]

        handle = application.ApplicationHandle()
        handle.Type = ApplicationHandle.MODULE
        if env.AppVersion is None:
            handle.Value = env.AppName
        else:
            handle.Value = env.AppName+"/"+env.AppVersion

        description = ""
        modvars = {}
        modfile = ' '.join(lines)
        for m in re.finditer("set (\S*)\s*\"([^\"]*)\"", modfile):
            if m is not None:
                # Replace \\n followed by whitespace in descriptions:
                sanitize = re.sub(r'\\\s+', ' ', m.group(2))
                modvars[m.group(1)] = sanitize
                # print(m.group(1)+"="+sanitize)
        #print("modvars keys, %s",modvars.keys())
        for line in lines:
            m = re.search("puts stderr \"([^\"]+)\"", line)
            if m is not None:
                if description != "":
                    description += " "
                description += m.group(1)
        if description != "":
            for modvar in list(modvars.keys()):
                if modvar in description:
                    description = description.replace(
                        "$"+modvar, modvars[modvar])
            description = description.replace("$_module_name", handle.Value)
            if env.AppVersion is not None:
                description = description.replace("$version", env.AppVersion)
            description = description.replace("\\t", " ")
            description = description.replace("\\n", "")
            description = re.sub(" +", " ", description)
            env.Description = description

        apps.add(env, [handle])

#######################################################################################################################


class ExtendedModApplicationsStep(application.ApplicationsStep):
    def __init__(self):
        application.ApplicationsStep.__init__(self)

        self._acceptParameter("exclude", "a comma-separated list of modules to ignore (default is to ignore none)",
                              False)
        self._acceptParameter("default_support_contact", "default to publish as SupportContact if no value is present in module file",
                              False)
        self._acceptParameter("recurse_module_dirs", "legacy behavior: assume that module_path dirs and their recursive subdirs contain at most one level of semantically important subdirs.",
                              False)
        self._acceptParameter("ignore_toplevel_modulefiles", "legacy behavior: assume that modulefiles at the top level of each module_path directory should not be reported as software.",
                              False)

    def _run(self):
        try:
            self.exclude = self.params["exclude"].split(",")
        except KeyError:
            self.exclude = []

        self.support_contact = self.params.get(
            "default_support_contact", False)
        self.recurse_module_dirs = self.params.get(
            "recurse_module_dirs", False)
        self.ignore_toplevel_modulefiles = self.params.get(
            "ignore_toplevel_modulefiles", False)

        apps = application.Applications(self.resource_name, self.ipfinfo)

        module_paths = []
        try:
            paths = os.environ["MODULEPATH"]
            module_paths.extend(list(map(os.path.realpath, paths.split(":"))))
        except KeyError:
            raise StepError("didn't find environment variable MODULEPATH")

        #if recursive is True:
        if self.recurse_module_dirs is True:
            for path in module_paths:
                self._addPathRecursive(path, path, module_paths, apps)
        else:
            for path in module_paths:
                self._traversePaths(path, path, module_paths, apps)
        return apps

    def _traversePaths(self, path, module_path, module_paths, apps):
        try:
            for filepath, dirs, files in os.walk(path, topdown=False):
                for f in files:
                    if f.startswith("."):
                        continue
                    if f.endswith("~"):
                        continue
                    if filepath.startswith(module_path):
                        name = filepath[len(module_path):].lstrip("/")
                    if name == "":
                        # this is a file int he top level of the path from
                        # MODULEPATH. Its name is the filename, and has no ver.
                        if self.ignore_toplevel_modulefiles is True:
                            continue
                        else:
                            name = f
                            ver = "undefined"
                    else:
                        ver = f

                    # print(f"module_path: {module_path}, \
                    # filepath: {filepath}, file: {f}, name: {name}")
                    if name not in self.exclude:
                        self._addModule(os.path.join(path, filepath, f),
                                        name, ver, apps)
        except OSError:
            return

    def _addPathRecursive(self, path, module_path, module_paths, apps):
        try:
            file_names = os.listdir(path)
        except OSError:
            return
        for file in file_names:
            if os.path.join(path, file) in module_paths:
                # don't visit other module paths
                continue
            if os.path.isdir(os.path.join(path, file)):
                self._addPath(os.path.join(path, file),
                              module_path, module_paths, apps)
            else:
                if path == module_path:
                    # if true, all files are top-level within a modulepath
                    # which we assume only load modules, and don't represent
                    # software
                    continue
                if file.startswith("."):
                    continue
                if file.endswith("~"):
                    continue
                name = os.path.basename(path)
                # ignore files in the top level of a "modulefiles" dir
                # if name != "modulefiles":
                if name not in self.exclude:
                    self._addModule(os.path.join(path, file), name, file, apps)

    def _addModule(self, path, name, version, apps):
        DEFAULT_VALIDITY = 60*60*24*7  # seconds in a week
        env = application.ApplicationEnvironment()
        env.AppName = name
        env.Validity = DEFAULT_VALIDITY
        publishflag = True
        # env.AppVersion set below, after massaging and/or reading from file

        try:
            file = open(path, "rb")
        except IOError as e:
            self.warning("%s" % e)
            return
        text = file.read().decode(errors='replace')
        file.close()

        # Take hash of path to uniquify the AppEnv and AppHandle IDs
        pathhashobject = hashlib.md5(str(path).encode('utf-8'))
        env.path_hash = pathhashobject.hexdigest()

        if not version.endswith(".lua"):
            # Weed out files that are not Module files
            m = re.search("#%Module", text)
            if m is None:
                return
        else:
            # correct version string to remove ".lua"
            version = version[:len(version)-4]
        env.AppVersion = version

        # Search both whatis([[]]) and general comments for these keywords
        # This regex strategy inspired by https://stackoverflow.com/a/33411504
        words = ['Name', 'Version', '.*escription', 'URL', 'Category', 'Keywords', 'SupportStatus', 'SupportContact', 'Default', 'IPF_FLAGS']
        longest_first = sorted(words, key=len, reverse=True)
        whatis_re = re.compile(r'whatis\(\[\[((?:{}))\s*:\s*(.*)\]\]\)'.format('|'.join(longest_first)))
        comment_re = re.compile(r'\"((?:{})):([^\"]+)\"'.format('|'.join(longest_first)))
        whatis_res = whatis_re.findall(text)
        comment_res = comment_re.findall(text)

        #Now we go through the combined list of tuples and add them to the
        #appropriate env.  Comments override whatis.
        for k,v in whatis_res+comment_res:
            if k == "Name":
                env.SpecifiedName = v
                #We're going to try overriding AppName as well, as spack/lmod
                #don't follow the same filenaming convention, so AppName is 
                #meaningless there
                env.AppName = v
            elif k == "Version":
                env.AppVersion = v
            elif "escription" in k:
                env.Description = v
            elif k == "URL":
                env.Repository = v
            elif k == "Category":
                env.Extension['Category'] = list(map(str.strip, v.split(',')))
            elif k == "Keywords":
                env.Keywords = list(map(str.strip, v.split(',')))
            elif k == "SupportStatus":
                # Is support status supposed to be a list?
                # supportstatus = []
                # supportstatus.append(list(map(str.strip, v.split(","))))
                env.Extension['SupportStatus'] = v
            elif k == "SupportContact":
                env.Extension['SupportContact'] = v
            elif k == "Default":
                env.Extension['Default'] = v
            elif k == "IPF_FLAGS":
                #Currently only supporting NOPUBLISH
                flagslist = list(
                    map(str.strip, v.split(",")))
                if "NOPUBLISH" in flagslist:
                    publishflag = False
                    self.debug("NOPUBLISH set")
        if env.Description is None:
            env.Description = self._InferDescription(text, env)
        if "SupportContact" not in env.Extension:
            self.debug("no SupportContact")
            if self.support_contact:
                env.Extension["SupportContact"] = self.support_contact



        handle = application.ApplicationHandle()
        handle.Type = ApplicationHandle.MODULE
        handle.Value = env.AppName+"/"+env.AppVersion
        env.ExecutionEnvironmentID = IPF_URN_PREFIX+"ExecutionEnvironment:%s" % (
            self.resource_name)

        if publishflag == True:
            apps.add(env, [handle])

    def _InferDescription(self, text, env):
        handle = application.ApplicationHandle()
        handle.Type = ApplicationHandle.MODULE
        if env.AppVersion is None:
            handle.Value = env.AppName
        else:
            handle.Value = env.AppName+"/"+env.AppVersion

        description = ""
        modvars = {}
        modfile = text
        for m in re.finditer("set (\S*)\s*\"([^\"]*)\"", modfile):
            if m is not None:
                # Replace \\n followed by whitespace in descriptions:
                sanitize = re.sub(r'\\\s+', ' ', m.group(2))
                modvars[m.group(1)] = sanitize
                # print(m.group(1)+"="+sanitize)
        desc_match = re.findall("puts stderr \"([^\"]+)\"", text)
        for line in desc_match:
            # self.debug("line is "+line)
            if description != "":
                description += " "
            description += line
        # self.debug("Description is "+description)
        if description != "":
            for modvar in list(modvars.keys()):
                if modvar in description:
                    description = description.replace(
                        "$"+modvar, modvars[modvar])
            description = description.replace("$_module_name", handle.Value)
        if env.AppVersion is not None:
            description = description.replace("$version", env.AppVersion)
            description = description.replace("\\t", " ")
            description = description.replace("\\n", "")
            description = re.sub(" +", " ", description)
        return description
