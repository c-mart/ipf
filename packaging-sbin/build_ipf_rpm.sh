#!/bin/bash
VERSION=`grep version ../setup.py |awk 'BEGIN { FS = "\"" } ; { print $2 }'`
echo "Version is $VERSION"\n
echo $VERSION >./VERSIONipf
VERSION=1.7.1
RELEASE=`cat ./RELEASE`
SDIDIR=`pwd`
cd ..

python ./setup.py bdist_rpm --spec-only
python setup.py sdist --formats=gztar
mkdir -p build/bdist.linux_x86_64/rpm/SOURCES/
if [ -e dist/ipf-xsede-$VERSION.tar.gz ]
  then
	echo "copying ipf-xsede"
	cp dist/ipf-xsede-$VERSION.tar.gz build/bdist.linux_x86_64/rpm/SOURCES/ipf-xsede-$VERSION.tar.gz
  else
	echo "copying ipf"
	cp dist/ipf-$VERSION.tar.gz build/bdist.linux_x86_64/rpm/SOURCES/ipf-$VERSION.tar.gz
fi
cp $SDIDIR/patches/ipf-rpm-only.patch build/bdist.linux_x86_64/rpm/SOURCES/ipf-rpm-only-mods.patch
ls -al build/bdist.linux_x86_64/rpm/SOURCES/ipf-$VERSION.tar.gz

#sed -i 's/--record=INSTALLED_FILES/--record=INSTALLED_FILES --prefix=\/etc/' dist/ipf-xsede-ipf.spec
#sed -i 's/Prefix: %{_prefix}/Prefix: %{_prefix}\nPrefix: \/etc/' dist/ipf.spec
gsed -i 's/Name: %{name}/Name: %{name}\nObsoletes: ipf-xsede/' dist/ipf.spec
gsed -i 's/Requires: python-amqp >= 1.4/AutoReq: no\nRequires: python3-amqp >= 1.4, python3,  python3-setuptools, /' dist/ipf.spec
gsed -i 's/python-dateutil/python3-dateutil/' dist/ipf.spec
#gsed -i 's/%define name ipf/%define name ipf-xsede/' dist/ipf.spec
gsed -i "s/%define release 1/%define release $RELEASE/" dist/ipf.spec
gsed -i "s/License: Apache/Patch0: ipf-rpm-only-mods.patch\nLicense: Apache/" dist/ipf.spec
gsed -i 's/%setup -n %{name}-%{unmangled_version} -n %{name}-%{unmangled_version}/%setup -n ipf-%{unmangled_version}\n\n%patch0 -p1/' dist/ipf.spec
gsed -i 's@%prep@%pre\n # user creation cribbed from\n # http://fedoraproject.org/wiki/Packaging%3aUsersAndGroups\n \ngetent group xdinfo >/dev/null || groupadd -r xdinfo\n getent passwd xdinfo >/dev/null || useradd -r -g xdinfo -s /sbin/nologin -c "Account for ACCESS-CI Information Services to own files or run processes" xdinfo\n exit 0\n\n%prep@' dist/ipf.spec
gsed -i 's@%defattr(-,root,root)@%defattr(-,xdinfo,xdinfo)\n%attr(-,xdinfo,xdinfo) /etc/ipf\n%%attr(-,xdinfo,xdinfo) /etc/ipf/workflow\n%attr(-,xdinfo,xdinfo) /etc/ipf/init.d\n%attr(-,xdinfo,xdinfo) /var/ipf\n%config(noreplace) /etc/ipf/init.d/ipf-WORKFLOW\n%config(noreplace) /etc/ipf/logging.conf\n%config(noreplace) /etc/ipf/workflow/sysinfo.json\n%config(noreplace) /etc/ipf/workflow/sysinfo_publish_periodic.json\n%config(noreplace) /etc/ipf/workflow/sysinfo_publish.json\n\n%post@' dist/ipf.spec
#munging shebang lines should happen in the install section (so, before clean)
gsed -i "s@%clean@gsed -i \'1 s/^.*$/#!\\\/usr\\\/bin\\\/python3/\' \$RPM_BUILD_ROOT/usr/bin/ipf_workflow\n%clean@" dist/ipf.spec
gsed -i "s@%clean@gsed -i \'1 s/^.*$/#!\\\/usr\\\/bin\\\/python3/\' \$RPM_BUILD_ROOT/usr/bin/ipf_configure\n%clean@" dist/ipf.spec
gsed -i "s@%post@%post\n\nsed -i \'s/IPF_USER=ipf/IPF_USER=xdinfo/\' /etc/ipf/init.d/ipf-WORKFLOW\n@" dist/ipf.spec
gsed -i 's/python3 setup.py install --single-version-externally-managed -O1 --root=$RPM_BUILD_ROOT --record=INSTALLED_FILES/python3 setup.py install --single-version-externally-managed -O1 --root=$RPM_BUILD_ROOT --record=INSTALLED_FILES --prefix=\/usr\//' dist/ipf.spec
CURRENTDIR=`pwd`
echo $CURRENTDIR
_PYTHON_PROJECT_BASE='/usr/'
echo $_PYTHON_PROJECT_BASE
rpmbuild --define "_prefix /usr" --define "_arch x86_64" --define "_topdir $CURRENTDIR/build/bdist.linux_x86_64/rpm" --ba --target x86_64-redhat-linux --clean dist/ipf.spec --verbose
#rpmbuild -ba --define "_topdir $CURRENTDIR/build/bdist.linux_x86_64/rpm" --clean dist/ipf.spec --verbose

mkdir -p $SDIDIR/dist
cp build/bdist.linux_x86_64/rpm/RPMS/noarch/ipf-$VERSION-$RELEASE.noarch.rpm $SDIDIR/dist/
cp build/bdist.linux_x86_64/rpm/SRPMS/ipf-$VERSION-$RELEASE.src.rpm $SDIDIR/dist/
cp dist/ipf-$VERSION.tar.gz $SDIDIR/dist/ipf-$VERSION.tar.gz

cd $SDIDIR
#./sbin/package ipf-xsede
