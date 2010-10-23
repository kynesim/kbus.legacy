package com.kynesim.kbus;

import java.util.*;

public class Ksock {
    private int ksock_fd;

    /* ---- NATIVE ---- */

    static {
        System.loadLibrary("jkbus");
    }

    private native int native_open(int device_number, int flags);
    private native int native_close(int ksock);

    private native int native_wait_for_message(int ksock, int waitfor);
 
    private native  com.kynesim.kbus.MessageId native_send_msg(int     ksock,
                                                               com.kynesim.kbus.Message  msg) throws KsockException;

    
    private native int native_bind(int ksock,  String name, long is_replier);
    private native int native_unbind(int ksock,  String name, long is_replier);
    private native com.kynesim.kbus.Message native_read_next_message(int ksock);

    /* ---- CONSTANTS ---- */

    public static final int KBUS_SOCK_READABLE  = (1 << 0);
    public static final int KBUS_SOCK_WRITEABLE = (1 << 1);



    /* ---- THERESTTM ---- */    

    /**
     * Constructor.
     *
     * @param which which KBUS device to open - so if 'which' is 3, 
     *        we open /dev/kbus3.  the text of the tool tip.
     *
     * @param mode should be 'r' or'rw' - i.e., whether to open the device for
     *        read or write (opening for write also allows reading, of course).
     */
    public Ksock(int which, String mode) throws KsockException {
        int flags = 0;

        if (mode != "r" && mode != "rw") {
            /* FIXME: Throw correct exception*/
            throw new KsockException();
        }

        /* quick and dirty, 0 for read 1 for read/write. */
        if (mode == "r") {
            flags = 0;
        } else {
            flags = 1;

        }
        
        ksock_fd = native_open(which, flags);
        
        System.out.printf("foo %d\n", ksock_fd);

        if (ksock_fd < 0) {
            throw  new KsockException();
        }                
    }



    /** 
     * Close the Ksock, no more opperations may be performed.
     */
    public void close() {

    }

    /**
     * Discard the message being written.
     *
     * Indicates that we have should throw away the message we've been 
     * writing. Has no effect if there is no current message being written
     * (for instance, because 'send' has already been called). be sent.
     */
    public void discard() {

    }

    /**
     * Return the integer file descriptor from our internal fd.
     * 
     * This allows a Ksock instance to be used in a call of select.select()
     * - so, for instance, on should be able to do:
     * (r, w, x) = select.select([ksock1, ksock2, ksock3], None, None)
     * instead of the (less friendly, but also valid):
     * (r, w, x) = select.select([ksock1.fd, ksock2.fd, ksock3.fd], None, None)
     */
    public void fileno() {

    }


    /**
     * Return the internal ‘Ksock id’ for this file descriptor.
     */
    public int ksock_fd() {
        
        return ksock_fd;
    }



    /**
     * Constructor.
     *
     * @param message the message to send.
     *
     * @return message id of the message just sent.
     */
    public MessageId send(Message message) throws KsockException {
        MessageId mid = null;
        
        try {
            mid = native_send_msg(ksock_fd, message);
        } catch (KsockException e) {
            System.out.printf("Failed While Sending: Exception " + e + "\n");
            throw e;
        }


        return mid;
    }

    /**
     * Wait until either the Ksock may be read from or written to.
     *
     * Returns when there is data to be read from the Ksock, or the Ksock
     * may be written to.
     *
     * @param wait_for indicates what to wait for. It should be set to
     * ``KBUS_SOCK_READABLE``, ``KBUS_SOCK_WRITABLE``, or the two "or"ed together,
     * as appropriate.
     *
     * @return ``KBUS_SOCK_READABLE``, ``KBUS_SOCK_WRITABLE``, or the two "or"ed
     * together to indicate which operation is ready, or a negative number
     * (``-errno``) for failure.
     */
    public int wait_for_message(int wait_for) throws KsockException{
        int rv = native_wait_for_message(ksock_fd, wait_for);

        if (rv < 0) {
            throw new KsockException("Waiting failed. (retval: " + rv + ")");
        }

        return rv;
    }



    public void bind(String name, boolean is_replier) throws KsockException {
        
        int rv = native_bind(ksock_fd, name, (is_replier)? 1: 0);

        if (rv < 0) {
            throw new KsockException("Failed to bind (retval: " + rv + ")");
        }

        return;
    }

    public void unbind(String name, boolean is_replier) throws KsockException {
        
        int rv = native_unbind(ksock_fd, name, (is_replier)? 1: 0);

        if (rv < 0) {
            throw new KsockException("Failed to bind (retval: " + rv + ")");
        }

        return;
    }

    public com.kynesim.kbus.Message read_next_message() throws KsockException {
        Message m = native_read_next_message(ksock_fd);

        if (m == null) {
            throw new KsockException("No message recived.");
        }

        return m;
    }



}