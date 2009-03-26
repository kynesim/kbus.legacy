"""Python code for testing the kbus kernel module.

Intended for use with (for instance) nose -- so, for instance::

    $ cd kernel_module
    $ make
    $ nosetests test_kbus.py -d
    ...........................
    ----------------------------------------------------------------------
    Ran 27 tests in 2.048s

    OK

To get the doctests (for instance, in kbus.py's Message) as well, try::

    nosetests kbus.py test_kbus.py -d --doctest-tests --with-doctest
"""

# ***** BEGIN LICENSE BLOCK *****
# Version: MPL 1.1
#
# The contents of this file are subject to the Mozilla Public License Version
# 1.1 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
# http://www.mozilla.org/MPL/
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License
# for the specific language governing rights and limitations under the
# License.
#
# The Original Code is the KBUS Lightweight Linux-kernel mediated
# message system
#
# The Initial Developer of the Original Code is Kynesim, Cambridge UK.
# Portions created by the Initial Developer are Copyright (C) 2009
# the Initial Developer. All Rights Reserved.
#
# Contributor(s):
#   Kynesim, Cambridge UK
#   Tibs <tony.ibbs@gmail.com>
#
# ***** END LICENSE BLOCK *****

from __future__ import with_statement

import sys
import os
import subprocess
import fcntl
import time
import array
import errno
import nose

from kbus import Interface, Message, Request, Reply
from kbus import read_bindings

NUM_DEVICES = 3

def setup_module():
    retcode = system('sudo insmod kbus.ko kbus_num_devices=%d'%NUM_DEVICES)
    assert retcode == 0
    # Via the magic of hotplugging, that should cause our device to exist
    # ...eventually
    time.sleep(1)

def teardown_module():
    retcode = system('sudo rmmod kbus')
    assert retcode == 0
    # Via the magic of hotplugging, that should cause our device to go away
    # ...eventually
    time.sleep(1)
    assert not os.path.exists("/dev/kbus0")

# Let's be good and not use os.system...
def system(command):
    """Taken from the Python reference manual. Thank you.
    """
    try:
        retcode = subprocess.call(command, shell=True)
        if retcode < 0:
            print "'%s' was terminated by signal %s"%(command,-retcode)
        else:
            print "'%s' returned %s"%(command,retcode)
        return retcode
    except OSError, e:
        print "Execution of '%s' failed: %s"%(command,e)

class BindingsMemory(object):
    """A class for remembering message name bindings.

    We remember bindings in a dictionary, relating Interface instances to
    bindings made on those interfaces. So, for instance:
    
       bindings[if] = [(True,False,'$.Fred.Jim.Bob'),
                       (False,True,'$.Fred')]
    
    (the order in the tuple matches that in the /proc/kbus/bindings file).
    
    Automatically managed by the local bind and unbind *methods*
    """

    def __init__(self):
        self.bindings = {}

    def remember_interface(self,interface):
        self.bindings[interface] = []

    def forget_interface(self,interface):
        del self.bindings[interface]

    def remember_binding(self,interface,name,replier=False,guaranteed=False):
        self.bindings[interface].append( (replier,guaranteed,name) )

    def forget_binding(self,interface,name,replier=False,guaranteed=False):
        if_list = self.bindings[interface]
        # If there are multiple matches, we'll delete the first,
        # which is what we want (well, to delete a single instance)
        for index,thing in enumerate(if_list):
            if thing[-1] == name:       # the name is always the last element
                del if_list[index]
                break
        # No matches shouldn't occur, but let's ignore it anyway

    def check_bindings(self):
        """Check the bindings we think we have match those of kbus
        """
        expected = []
        for interface,if_list in self.bindings.items():
            for r,a,n in if_list:
                expected.append( (interface,r,a,n) )
        assert bindings_match(expected)

class RecordingInterface(Interface):
    """A variant of Interface which remembers and checks its bindings.

    Intended originally for use in writing test code.

    The constructor takes an extra argument, which should be a BindingsMemory
    instance, and which is used to remember our bindings. Otherwise, use it
    just like an ordinary Interface.
    """

    def __init__(self, which=0, mode='r', bindings=None):
        super(RecordingInterface,self).__init__(which,mode)
        self.bindings = bindings
        self.bindings.remember_interface(self)

    def close(self):
        super(RecordingInterface,self).close()
        self.bindings.forget_interface(self)
        self.bindings = None

    def bind(self,name,replier=False,guaranteed=False):
        """A wrapper around the 'bind' function. to keep track of bindings.
        """
        super(RecordingInterface,self).bind(name,replier,guaranteed)
        self.bindings.remember_binding(self,name,replier,guaranteed)

    def unbind(self,name,replier=False,guaranteed=False):
        """A wrapper around the 'unbind' function, to keep track of bindings.
        """
        super(RecordingInterface,self).unbind(name,replier,guaranteed)
        self.bindings.forget_binding(self,name,replier,guaranteed)

def str_rep(rep):
    if rep:
        return 'R'
    else:
        return 'L'

def str_all(all):
    if all:
        return 'T'
    else:
        return 'F'

def bindings_match(bindings):
    """Look up the current bindings and check they match the list.

    'bindings' is a sequence of tuples, each of the form:

        ( file_descriptor, True|False, True|False, name )

    so for instance:

        ( (f,True,True,'$.Fred'), (g,False,False,'$.JimBob') )

    where the first True means the binding is for a replier (or not), and the
    second means it wants to guarantee to receive all its messages (or not).

    The function reads the contents of /proc/kbus/bindings. It translates each
    file descriptor to a listener id using ``bound_as``, and thus converts
    'bindings' to an equivalent list.

    Silently returns True if the bindings in /proc/kbus/bindings match
    those expected, returns False (and prints out the mismatch) if they do not.
    """
    testwith = []
    names = {}
    for (fd,rep,all,name) in bindings:
        if fd not in names:
            names[fd] = fd.bound_as()
        testwith.append((fd.bound_as(),rep,all,name))

    actual = read_bindings(names)

    # And compare the two lists - ideally they should match
    # (although we don't want to care about order, I think)
    actual.sort()
    testwith.sort()
    if actual == testwith:
        return True

    # If they're not the same, we need to let the user know in some not too
    # unfriendly manner
    found    = set(actual)
    expected = set(testwith)
    print 'The contents of /proc/kbus/bindings is not as expected'
    if len(found):
        print 'The following were expected but not found:'
        for f,r,a,n in expected-found:
            print '  %10u %c %c %s'%(f,str_rep(r),str_all(a),n)
    if len(expected):
        print 'The following were found but not expected:'
        for f,r,a,n in found-expected:
            print '  %10u %c %c %s'%(f,str_rep(r),str_all(a),n)
    return False

def check_IOError(expected_errno,fn,*stuff):
    """When calling apply(fn,stuff), check for IOError with the given errno.

    Check that is what happens...
    """
    try:
        apply(fn,stuff)
        # We're not expecting to get here...
        assert False, 'Applying %s%s did not fail with IOError'%(repr(fn),repr(stuff))
    except IOError, e:
        actual_errno = e.args[0]
        errno_name = errno.errorcode[actual_errno]
        expected_errno_name = errno.errorcode[expected_errno]
        assert actual_errno == expected_errno, \
                'expected %s, got %s'%(expected_errno_name,errno_name)
    except Exception, e:
        print e
        assert False, 'Applying %s%s failed with %s, not IOError'%(repr(fn),
                repr(stuff),sys.exc_type)

class TestInterface:
    """Some basic testing of Interface.

    Not much here, because most of its testing is done implicitly via
    its use in other tests. And it really is fairly simple.
    """

    def test_opening(self):
        """Test opening/closing Interface objects.
        """
        # We should be able to open each device that exists
        for ii in range(NUM_DEVICES):
            f = Interface(ii)
            f.close()
        # and not those that don't
        check_IOError(errno.ENOENT,Interface,-1)
        check_IOError(errno.ENOENT,Interface,NUM_DEVICES)

    def test_modes(self):
        """Test only the allowed modes are allowed
        """
        f = Interface(0,'r')
        f.close()
        f = Interface(0,'rw')
        f.close()
        nose.tools.assert_raises(ValueError,Interface,0,'fred')
        nose.tools.assert_raises(ValueError,Interface,0,'w+')
        nose.tools.assert_raises(ValueError,Interface,0,'x')

class TestKernelModule:

    def __init__(self):
        self.bindings = BindingsMemory()

    def _check_bindings(self):
        self.bindings.check_bindings()

    def _check_read(self,f,expected):
        """Check that we can read back an equivalent message to 'expected'
        """
        if expected:
            new_message = f.read()
            assert new_message != None
            assert expected.equivalent(new_message)
        else:
            # We're not expecting anything -- check that's what we get
            # - first, directly
            data = f.fd.read(1)
            assert data == ''
            # - secondly, in terms of Interface and Message
            assert f.read() == None

    def test_readonly(self):
        """If we open the device readonly, we can't do much(!)
        """
        f = RecordingInterface(0,'r',self.bindings)
        assert f != None
        try:
            # Nothing to read
            assert f.read() == None

            # We can't write to it
            msg2 = Message('$.Fred','data')
            check_IOError(errno.EBADF,f.write,msg2)
        finally:
            assert f.close() is None

    def test_readwrite_kbus0(self):
        """If we open the device read/write, we can read and write.
        """
        f = RecordingInterface(0,'rw',self.bindings)
        assert f != None

        try:
            f.bind('$.B')
            f.bind('$.C')

            # We start off with no message
            self._check_read(f,None)

            # We can write a message and read it back
            msg1 = Message('$.B','data')
            f.write(msg1)
            self._check_read(f,msg1)

            # We can write a message and read it back, again
            msg2 = Message('$.C','fred')
            f.write(msg2)
            self._check_read(f,msg2)

            # If we try to write a message that nobody is listening for,
            # we get an appropriate error
            msg3 = Message('$.D','fred')
            check_IOError(errno.EADDRNOTAVAIL,f.write,msg3)

        finally:
            assert f.close() is None

    def test_two_opens_kbus0(self):
        """If we open the device multiple times, they communicate
        """
        f1 = RecordingInterface(0,'rw',self.bindings)
        assert f1 != None
        try:
            f2 = RecordingInterface(0,'rw',self.bindings)
            assert f2 != None
            try:
                # Both files listen to both messages
                f1.bind('$.B',False)
                f1.bind('$.C',False)
                f2.bind('$.B',False)
                f2.bind('$.C',False)

                # Nothing to read at the start
                self._check_read(f1,None)
                self._check_read(f2,None)

                # If we write, we can read appropriately
                msg1 = Message('$.B','data')
                f1.write(msg1)
                self._check_read(f2,msg1)
                self._check_read(f1,msg1)

                msg2 = Message('$.C','data')
                f2.write(msg2)
                self._check_read(f1,msg2)
                self._check_read(f2,msg2)
            finally:
                assert f2.close() is None
        finally:
            assert f1.close() is None

    def test_bind(self):
        """Initial ioctl/bind test.
        """
        f = RecordingInterface(0,'rw',self.bindings)
        assert f != None

        try:
            # - BIND
            # Low level check: The "Bind" ioctl requires a proper argument
            check_IOError(errno.EINVAL, fcntl.ioctl, f.fd, Interface.KBUS_IOC_BIND, 0)
            # Said string must not be zero length
            check_IOError(errno.EBADMSG, f.bind, '', True)
            f.bind('$.Fred')
            # - UNBIND
            check_IOError(errno.EINVAL, fcntl.ioctl, f.fd, Interface.KBUS_IOC_UNBIND, 0)
            check_IOError(errno.EBADMSG, f.unbind, '', True)
            f.unbind('$.Fred')
        finally:
            assert f.close() is None

    def test_many_bind_1(self):
        """Initial ioctl/bind test -- make lots of bindings
        """
        f = RecordingInterface(0,'rw',self.bindings)
        assert f != None

        try:
            f.bind('$.Fred')
            f.bind('$.Fred.Jim')
            f.bind('$.Fred.Bob')
            f.bind('$.Fred.Jim.Bob')
        finally:
            assert f.close() is None

    def test_many_bind_2(self):
        """Initial ioctl/bind test -- make lots of the same binding
        """
        f = RecordingInterface(0,'rw',self.bindings)
        assert f != None

        try:
            f.bind('$.Fred')
            f.bind('$.Fred',False)
            f.bind('$.Fred',False)
            f.bind('$.Fred',False)
        finally:
            assert f.close() is None

    def test_many_bind_3(self):
        """Initial ioctl/bind test -- multiple matching bindings/unbindings
        """
        f = RecordingInterface(0,'rw',self.bindings)
        assert f != None

        try:
            f.bind('$.Fred',True)  # But remember, only one replier
            f.bind('$.Fred',False)
            f.bind('$.Fred',False)
            f.unbind('$.Fred',True)
            f.unbind('$.Fred',False)
            f.unbind('$.Fred',False)
            # But not too many
            check_IOError(errno.EINVAL, f.unbind, '$.Fred')
            check_IOError(errno.EINVAL, f.unbind, '$.Fred',False)
            # We can't unbind something we've not bound
            check_IOError(errno.EINVAL, f.unbind, '$.JimBob',False)
        finally:
            assert f.close() is None

    def test_bind_more(self):
        """Initial ioctl/bind test - with more bindings.
        """
        f1 = RecordingInterface(0,'rw',self.bindings)
        assert f1 != None
        try:
            f2 = RecordingInterface(0,'rw',self.bindings)
            assert f2 != None
            try:
                # We can bind and unbind
                f1.bind('$.Fred',replier=True)
                f1.unbind( '$.Fred',replier=True)
                f1.bind('$.Fred',replier=False)
                f1.unbind( '$.Fred',replier=False)
                # We can bind many times
                f1.bind('$.Fred',replier=False)
                f1.bind('$.Fred',replier=False)
                f1.bind('$.Fred',replier=False)
                # But we can only have one replier
                f1.bind('$.Fred',replier=True)
                check_IOError(errno.EADDRINUSE, f1.bind, '$.Fred',True)

                # Two files can bind to the same thing
                f1.bind('$.Jim.Bob',replier=False)
                f2.bind('$.Jim.Bob',replier=False)
                # But we can still only have one replier
                f1.bind('$.Jim.Bob',replier=True)
                check_IOError(errno.EADDRINUSE, f2.bind, '$.Jim.Bob', True)

                # Oh, and not all messages need to be received
                # - in our interfaces, we default to allowing kbus to drop
                # messages if necessary
                f1.bind('$.Jim.Bob',replier=False,guaranteed=True)
                f1.bind('$.Fred',replier=False,guaranteed=True)
            finally:
                assert f2.close() is None
        finally:
            assert f1.close() is None

    def test_bindings_match1(self):
        """Check that bindings match inside and out.
        """
        f1 = RecordingInterface(0,'rw',self.bindings)
        assert f1 != None
        try:
            f2 = RecordingInterface(0,'rw',self.bindings)
            assert f2 != None
            try:
                f1.bind('$.Fred',True)
                f1.bind('$.Fred.Jim',True)
                f1.bind('$.Fred.Bob',True)
                f1.bind('$.Fred.Jim.Bob',True)
                f1.bind('$.Fred.Jim.Derek')
                # /proc/kbus/bindings should reflect all of the above, and none other
                self._check_bindings()
                f2.bind('$.Fred.Jim.Derek')
                f2.bind('$.William')
                f2.bind('$.William')
                f2.bind('$.William')
                f1.bind('$.Fred.Jim.Bob.Eric',True)
                self._check_bindings()
            finally:
                assert f2.close() is None
        finally:
            assert f1.close() is None
        # And now all of the bindings *should* have gone away
        self._check_bindings()

    def test_rw_single_file(self):
        """Test reading and writing two messages on a single file
        """
        f = RecordingInterface(0,'rw',self.bindings)
        assert f != None
        try:

            name1 = '$.Fred.Jim'
            data1 = array.array('L','datadata')

            name2 = '$.Fred.Bob.William'
            data2 = array.array('L','This is surely some data')

            # Bind so that we can write/read the first, but not the second
            f.bind(name1,False)
            f.bind('$.William',False)

            msg1 = Message(name1,data=data1)
            f.write(msg1)
            print 'Wrote:',msg1

            # There are no listeners for '$.Fred.Bob.William'
            msg2 = Message(name2,data=data2)
            check_IOError(errno.EADDRNOTAVAIL, f.write, msg2)

            msg1r = f.read()
            print 'Read: ',msg1r

            # The message read should essentially match
            assert msg1.equivalent(msg1r)

            msg2r = f.read()
            assert msg2r == None

            # There shouldn't be anything else to read
            assert f.read() == None

        finally:
            assert f.close() is None

    def test_read_write_2files(self):
        """Test reading and writing between two files.
        """
        f1 = RecordingInterface(0,'rw',self.bindings)
        assert f1 != None
        try:
            f2 = RecordingInterface(0,'rw',self.bindings)
            assert f2 != None
            try:
                f1.bind('$.Fred',False)
                f1.bind('$.Fred',False)
                f1.bind('$.Fred',False)

                f2.bind('$.Jim',False)

                # Writing to $.Fred on f1 - writes message id N
                msgF = Message('$.Fred','data')
                f1.write(msgF)
                n = f1.last_msg_id()

                # No one is listening for $.William
                msgW = Message('$.William')
                check_IOError(errno.EADDRNOTAVAIL, f1.write, msgW)
                check_IOError(errno.EADDRNOTAVAIL, f2.write, msgW)
                # (and attempting to write it doesn't increment KBUS's
                # counting of the message id)

                # Writing to $.Jim on f1 - writes message N+1
                msgJ = Message('$.Jim','moredata')
                f1.write(msgJ)
                assert f1.last_msg_id() == n+1

                # Reading f1 - message N
                assert f1.next_len() == msgF.length*4
                # By the way - it's still the next length until we read
                assert f1.next_len() == msgF.length*4
                data = f1.read()
                # Extract the message id -- this is N
                n0 = data.extract()[0]
                assert n == n0

                # Reading f2 - should be message N+1
                assert f2.next_len() == msgJ.length*4
                data = f2.read()
                n3 = data.extract()[0]
                assert n3 == n0+1

                # Reading f1 - should be message N again
                assert f1.next_len() == msgF.length*4
                data = f1.read()
                n1 = data.extract()[0]
                assert n1 == n0

                # Reading f1 - should be message N again
                assert f1.next_len() == msgF.length*4
                data = f1.read()
                n2 = data.extract()[0]
                assert n2 == n0

                # No more messages on f1
                assert f1.next_len() == 0
                assert f1.read() == None

                # No more messages on f2
                assert f2.next_len() == 0
                assert f2.read() == None
            finally:
                assert f2.close() is None
        finally:
            assert f1.close() is None

    def test_message_names(self):
        """Test for message name legality.
        """
        f = RecordingInterface(0,'rw',self.bindings)
        assert f != None
        try:

            def _error(error,name):
                check_IOError(error, f.bind, name, True)

            def _ok(name):
                f.bind(name,True)

            # I don't necessarily know what name will be "too long",
            # but we can make a good guess as to a silly sort of length
            _error(errno.ENAMETOOLONG,'1234567890'*1000)

            # We need a leading '$.'
            _error(errno.EBADMSG,'')
            _error(errno.EBADMSG,'$')
            _error(errno.EBADMSG,'$x')
            _error(errno.EBADMSG,'Fred')

            _error(errno.EBADMSG,"$.Non-alphanumerics aren't allowed")
            _error(errno.EBADMSG,'$.#')

            # We cannot end with a dot
            _error(errno.EBADMSG,'$.Fred.')
            _error(errno.EBADMSG,'$.Fred..')
            # Or have two dots in a row
            _error(errno.EBADMSG,'$.Fred..Jim')
            _error(errno.EBADMSG,'$.Fred...Jim')
            _error(errno.EBADMSG,'$.Fred....Jim')

            # The following *are* legal
            _ok('$.Fred.Jim')
            _ok('$.Fred.Jim.Fred.Jim.MoreNames.And.More')
            _ok('$.QuiteLongWordsAreAllowedInNames')
            # Case matters
            _ok('$.This.is.a.different.name')
            _ok('$.THIS.is.a.different.name')
            # Top level wildcards are OK
            _ok('$.*')
            _ok('$.%')
        
        finally:
            assert f.close() is None

    def test_data_too_long(self):
        """Test for message name legality.
        """
        f = RecordingInterface(0,'rw',self.bindings)
        assert f != None
        try:
            # I don't necessarily know how much data will be "too long",
            # but we can make a good guess as to a silly sort of length
            m = Message('$.Fred',data='12345678'*1000)
            f.bind('$.Fred')
            check_IOError(errno.EMSGSIZE, f.write, m)
        finally:
            assert f.close() is None

    def test_cant_write_to_wildcard(self):
        """It's not possible to write a message with a wildcard name.
        """
        f = RecordingInterface(0,'rw',self.bindings)
        assert f != None
        try:
            # Listen with a wildcard - this is OK
            f.bind('$.Fred.*')
            # Create a message with a silly name - Message doesn't care
            m = Message('$.Fred.*')
            # Try to write it -- this shall not work
            check_IOError(errno.EBADMSG, f.write, m)
            # Try a different wildcard
            f.bind('$.Jim.%')
            m = Message('$.Jim.%')
            check_IOError(errno.EBADMSG, f.write, m)
        finally:
            assert f.close() is None

    def test_request_vs_message(self):
        """Test repliers and Requests versus Messages
        """
        with RecordingInterface(0,'rw',self.bindings) as f0:
            with RecordingInterface(0,'r',self.bindings) as listener:
                listener.bind('$.Fred.Message',False)
                
                # A listener receives Messages
                m = Message('$.Fred.Message')
                f0.write(m)
                r = listener.read()
                assert r.equivalent(m)
                assert not r.should_reply()

                # And it receives Requests (although it need not reply)
                m = Request('$.Fred.Message')
                f0.write(m)
                r = listener.read()
                assert r.equivalent(m)
                assert not r.should_reply()

                with RecordingInterface(0,'r',self.bindings) as replier:
                    replier.bind('$.Fred.Message',True)
                    
                    # A replier does not receive Messages
                    # (presumably the listener still does, but we're not going
                    # to check)
                    m = Message('$.Fred.Message')
                    f0.write(m)
                    assert replier.next_len() == 0

                    # But it does receive Requests (and it should reply)
                    m = Request('$.Fred.Message')
                    f0.write(m)
                    r = replier.read()
                    assert r.equivalent(m)
                    assert r.should_reply()

    def test_wildcards_a_bit(self):
        """Some initial testing of wildcards. And use of 'with'
        """
        with RecordingInterface(0,'rw',self.bindings) as f:
            assert f != None
            # Note, binding just as a listener
            f.bind('$.Fred.*',False)

            # We should receive the message, it matches the wildcard
            m = Message('$.Fred.Jim')
            f.write(m)
            r = f.read()
            assert r.equivalent(m)

            # And again
            m = Message('$.Fred.JimBob.William')
            f.write(m)
            r = f.read()
            assert r.equivalent(m)

            # But this does not match the wildcard
            m = Message('$.Fred')
            check_IOError(errno.EADDRNOTAVAIL, f.write, m)

            # A more specific binding, overlapping the wildcard
            # Since we're bound as (just) a listener both times,
            # we should get the message twice, once for each binding
            f.bind('$.Fred.Jim',False)
            m = Message('$.Fred.Jim')
            f.write(m)
            r = f.read()
            assert r.equivalent(m)
            r = f.read()
            assert r.equivalent(m)

    def test_wildcards_a_bit_more(self):
        """Some more initial testing of wildcards. And use of 'with'
        """
        with RecordingInterface(0,'rw',self.bindings) as f:
            assert f != None
            # Note, binding as a default replier
            f.bind('$.Fred.*',True)

            # We should receive the message, it matches the wildcard
            m = Request('$.Fred.Jim')
            f.write(m)
            r = f.read()
            assert r.equivalent(m)
            assert r.should_reply()

            # And again
            m = Request('$.Fred.JimBob.William')
            f.write(m)
            r = f.read()
            assert r.equivalent(m)
            assert r.should_reply()

            # But this does not match the wildcard
            m = Request('$.Fred')
            check_IOError(errno.EADDRNOTAVAIL, f.write, m)

            # A more specific binding, overlapping the wildcard
            f.bind('$.Fred.Jim',True)
            m = Request('$.Fred.Jim')
            f.write(m)
            r = f.read()
            assert r.equivalent(m)
            assert r.should_reply()

            # But we should only receive it once, on the more specific binding
            assert f.next_len() == 0

    def test_message_equality(self):
        """Messages are not equal to non-messages, and so on.
        """
        a = Message('$.Fred')
        b = Message('$.Fred')
        c = Message('$.Jim')
        assert (a == b)
        assert (a != c)

        assert (a ==    3) == False
        assert (a == None) == False
        assert (a !=    3) == True
        assert (a != None) == True

        assert (3    == a) == False
        assert (None == a) == False
        assert (3    != a) == True
        assert (None != a) == True

    def test_iteration(self):
        """Test we can iterate over messages.
        """
        with RecordingInterface(0,'rw',self.bindings) as f:
            assert f != None
            f.bind('$.Fred')
            m = Message('$.Fred')
            for ii in range(5):
                f.write(m)
            count = 0
            for r in f:
                count += 1
            assert count == 5
            # And again
            for ii in range(5):
                f.write(m)
            count = 0
            for r in f:
                count += 1
            assert count == 5

    def test_wildcard_listening_1(self):
        """Test using wildcards to listen - 1, asterisk.
        """
        with RecordingInterface(0,'rw',self.bindings) as f0:

            with RecordingInterface(0,'r',self.bindings) as f1:
                f1.bind('$.This.Fred')
                f1.bind('$.That.Fred')

                with RecordingInterface(0,'r',self.bindings) as f2:
                    f2.bind('$.This.Jim.One')
                    f2.bind('$.This.Jim.Two')
                    f2.bind('$.That.Jim')

                    with RecordingInterface(0,'r',self.bindings) as f3:
                        f3.bind('$.This.*')

                        # For each tuple, we have:
                        #
                        # 1. The Interface we're meant to be sending the
                        #    message to
                        # 2. Whether it should be "seen" by f0 (via f0's
                        #    wildcard binding)
                        # 3. The actual message
                        msgs = [ (f1, True,  Message('$.This.Fred','dat1')),
                                 (f1, True,  Message('$.This.Fred','dat2')),
                                 (f1, False, Message('$.That.Fred','dat3')),
                                 (f1, False, Message('$.That.Fred','dat4')),
                                 (f2, True,  Message('$.This.Jim.One','dat1')),
                                 (f2, True,  Message('$.This.Jim.Two','dat2')),
                                 (f2, False, Message('$.That.Jim','dat3')),
                                 (f2, False, Message('$.That.Jim','dat4')),
                                ]

                        for fd,wild,m in msgs:
                            f0.write(m)

                        for fd,wild,m in msgs:
                            if wild:
                                # This is a message that f3 should see
                                a = f3.read()
                                assert a.equivalent(m)

                            # Who else should see this message?
                            b = fd.read()
                            assert b.equivalent(m)

    def test_wildcard_listening_2(self):
        """Test using wildcards to listen - 2, percent.
        """
        with RecordingInterface(0,'rw',self.bindings) as f0:

            with RecordingInterface(0,'r',self.bindings) as f1:
                f1.bind('$.This.Fred')
                f1.bind('$.That.Fred')

                with RecordingInterface(0,'r',self.bindings) as f2:
                    f2.bind('$.This.Jim.One')
                    f2.bind('$.This.Jim.Two')
                    f2.bind('$.That.Jim')

                    with RecordingInterface(0,'r',self.bindings) as f3:
                        f3.bind('$.This.%')

                        # For each tuple, we have:
                        #
                        # 1. The Interface we're meant to be sending the
                        #    message to
                        # 2. Whether it should be "seen" by f0 (via f0's
                        #    wildcard binding)
                        # 3. The actual message
                        msgs = [ (f1, True,  Message('$.This.Fred','dat1')),
                                 (f1, True,  Message('$.This.Fred','dat2')),
                                 (f1, False, Message('$.That.Fred','dat3')),
                                 (f1, False, Message('$.That.Fred','dat4')),
                                 (f2, False, Message('$.This.Jim.One','dat1')),
                                 (f2, False, Message('$.This.Jim.Two','dat2')),
                                 (f2, False, Message('$.That.Jim','dat3')),
                                 (f2, False, Message('$.That.Jim','dat4')),
                                ]

                        for fd,wild,m in msgs:
                            f0.write(m)

                        for fd,wild,m in msgs:
                            if wild:
                                # This is a message that f3 should see
                                a = f3.read()
                                assert a.equivalent(m)

                            # Who else should see this message?
                            b = fd.read()
                            assert b.equivalent(m)

    def test_reply_single_file(self):
        """Test replying with a single file
        """
        with RecordingInterface(0,'rw',self.bindings) as f:
            name1 = '$.Fred.Jim'
            name2 = '$.Fred.Bob.William'
            name3 = '$.Fred.Bob.Jonathan'

            f.bind(name1,True)     # replier
            f.bind(name1,False)    # and listener
            f.bind(name2,True)     # replier
            f.bind(name3,False)    # listener

            msg1 = Message(name1,data='dat1')
            msg2 = Request(name2,data='dat2')
            msg3 = Request(name3,data='dat3')

            f.write(msg1)
            f.write(msg2)
            f.write(msg3)

            m1 = f.read()
            m2 = f.read()
            m3 = f.read()

            # For message 1, we only see it as a listener
            # (because it is not a Request) so there is no reply needed
            assert not m1.should_reply()

            # For message 2, a reply is wanted, and we are the replier
            assert m2.should_reply()

            # For message 3, a reply is wanted, but we are just a listener
            assert not m3.should_reply()

            # So, we should reply to message 2 - let's do so

            # We can make a reply "by hand" - remember that we want to
            # reply to the message we *received*, which has the id set
            # (by KBUS)
            (id,in_reply_to,to,from_,flags,name,data_array) = m2.extract()
            reply_by_hand = Message(name, data=None, in_reply_to=id, to=from_)

            # But it is easier to use the pre-packaged mechanism
            reply = Reply(m2)

            # These should, however, give the same result
            assert reply == reply_by_hand

            # And the obvious thing to do with a reply is
            f.write(reply)

            # We should receive that reply, even though we're not
            # a listener for the message (that's the *point* of replies)
            m4 = f.read()
            assert m4.equivalent(reply)

            # And there shouldn't be anything else to read
            assert f.next_len() == 0

    def test_reply_three_files(self):
        """Test replying with two files in dialogue, and another listening
        """
        with RecordingInterface(0,'r',self.bindings) as listener:
            listener.bind('$.*')

            with RecordingInterface(0,'rw',self.bindings) as writer:

                with RecordingInterface(0,'rw',self.bindings) as replier:
                    replier.bind('$.Fred',replier=True)

                    msg1 = Message('$.Fred')    # no reply necessary
                    msg2 = Request('$.Fred')

                    writer.write(msg1)
                    writer.write(msg2)

                    # The replier should not see msg1
                    # But it should see msg2, which should ask *us* for a reply
                    rec2 = replier.read()
                    assert rec2.should_reply()
                    assert rec2.equivalent(msg2)

                    # Which we can reply to
                    rep = Reply(msg2)
                    replier.write(rep)
                    assert not rep.should_reply()       # just to check!

                    # But should not receive
                    assert replier.next_len() == 0

                    # The listener should get all of those messages
                    # (the originals and the reply)
                    # but should not be the replier for any of them
                    a = listener.read()
                    assert a.equivalent(msg1)
                    assert not a.should_reply()
                    b = listener.read()
                    assert b.equivalent(msg2)
                    assert not b.should_reply()
                    c = listener.read()
                    assert c.equivalent(rep)
                    assert not c.should_reply()

                    # No-one should have any more messages
                    assert listener.next_len() == 0
                    assert writer.next_len()   == 0
                    assert replier.next_len()  == 0

    def test_wildcard_generic_vs_specific_bind_1(self):
        """Test generic versus specific wildcard binding - fit the first
        """
        with RecordingInterface(0,'rw',self.bindings) as f0:
            # We'll use this interface to do all the writing of requests,
            # just to keep life simple.

            with RecordingInterface(0,'r',self.bindings) as f1:
                # f1 asks for generic replier status on everything below '$.Fred'
                f1.bind('$.Fred.*',replier=True)

                mJim = Request('$.Fred.Jim')
                f0.write(mJim)
                r = f1.read()
                assert r.should_reply()
                assert r.equivalent(mJim)

                assert f1.next_len() == 0

                # Hmm - apart from existential worries, nothing happens if we
                # don't *actually* reply..

                with RecordingInterface(0,'r',self.bindings) as f2:
                    # f2 knows it wants specific replier status on '$.Fred.Jim'
                    f2.bind('$.Fred.Jim',replier=True)

                    # So, now, any requests to '$.Fred.Jim' should only go to
                    # f2, who should need to reply to them.
                    # Any requests to '$.Fred.Bob' should only go to f1, who
                    # should need to reply to them.
                    mBob = Request('$.Fred.Bob')

                    f0.write(mJim)      # should only go to f2
                    f0.write(mBob)      # should only go to f1

                    rJim = f2.read()
                    assert rJim.should_reply()
                    assert rJim.equivalent(mJim)
                    assert f2.next_len() == 0

                    rBob = f1.read()
                    assert rBob.should_reply()
                    assert rBob.equivalent(mBob)
                    assert f1.next_len() == 0

    def test_wildcard_generic_vs_specific_bind_2(self):
        """Test generic versus specific wildcard binding - fit the second
        """
        with RecordingInterface(0,'rw',self.bindings) as f0:
            # We'll use this interface to do all the writing of requests,
            # just to keep life simple.

            with RecordingInterface(0,'r',self.bindings) as f1:
                # f1 asks for generic replier status on everything below '$.Fred'
                f1.bind('$.Fred.*',replier=True)

                mJim = Request('$.Fred.Jim')
                f0.write(mJim)
                r = f1.read()
                assert r.should_reply()
                assert r.equivalent(mJim)

                assert f1.next_len() == 0

                # Hmm - apart from existential worries, nothing happens if we
                # don't *actually* reply..

                with RecordingInterface(0,'r',self.bindings) as f2:
                    # f2 gets more specific
                    f2.bind('$.Fred.%',replier=True)

                    # So, now, any requests to '$.Fred.Jim' should only go to
                    # f2, who should need to reply to them.
                    # Any requests to '$.Fred.Jim.Bob' should only go to f1,
                    # who should need to reply to them.
                    mJimBob = Request('$.Fred.Jim.Bob')

                    f0.write(mJim)      # should only go to f2
                    f0.write(mJimBob)   # should only go to f1

                    rJim = f2.read()
                    assert rJim.should_reply()
                    assert rJim.equivalent(mJim)
                    assert f2.next_len() == 0

                    rJimBob = f1.read()
                    assert rJimBob.should_reply()
                    assert rJimBob.equivalent(mJimBob)
                    assert f1.next_len() == 0

                    with RecordingInterface(0,'r',self.bindings) as f3:
                        # f3 knows it wants specific replier status on '$.Fred.Jim'
                        f3.bind('$.Fred.Jim',replier=True)

                        # So, now, any requests to '$.Fred.Jim' should only go to
                        # f3, who should need to reply to them.
                        # Any requests to '$.Fred.James' should still go to f2
                        # Any requests to '$.Fred.Jim.Bob' should still only go to f1
                        mJames = Request('$.Fred.James')

                        f0.write(mJim)      # should only go to f3
                        f0.write(mJames)    # should only go to f2
                        f0.write(mJimBob)   # should only go to f1

                        rJim = f3.read()
                        assert rJim.should_reply()
                        assert rJim.equivalent(mJim)
                        assert f3.next_len() == 0

                        rJames = f2.read()
                        assert rJames.should_reply()
                        assert rJames.equivalent(mJames)
                        assert f2.next_len() == 0

                        rJimBob = f1.read()
                        assert rJimBob.should_reply()
                        assert rJimBob.equivalent(mJimBob)
                        assert f1.next_len() == 0

#    def test_partial_read(self):
#        """Test partial read support.
#        """
#        fd = open('/dev/kbus0','r+b',1)
#        assert fd != None
#
#        try:
#
#            from kbus import KbusBindStruct
#
#            name = '$.Fred'
#            arg = KbusBindStruct(0,0,len(name),name)
#            fcntl.ioctl(fd, Interface.KBUS_IOC_BIND, arg)
#
#            m = Message(name,'data')
#            m.array.tofile(fd)
#
#            # We wish to be able to read it back in pieces
#            l = fcntl.ioctl(fd, Interface.KBUS_IOC_NEXTMSG, 0)
#            # Let's go for the worst possible case - byte by byte
#            data = ''
#            for ii in range(l):
#                c = fd.read(1)
#                assert c != ''
#                assert len(c) == 1
#                data += c
#
#            r = Message(data)
#            assert r.equivalent(m)
#
#        finally:
#            fd.close()


# vim: set tabstop=8 shiftwidth=4 expandtab: