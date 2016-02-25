Plugin Context
====================

.. automodule:: csmpe.context

PluginContext Class
-------------------

.. autoclass:: PluginContext
   :members: connect

   .. automethod:: __init__
   .. automethod:: condoor.Connection.connect
   .. automethod:: condoor.Connection.disconnect
   .. automethod:: condoor.Connection.reconnect
   .. automethod:: condoor.Connection.discovery
   .. automethod:: condoor.platforms.generic.Connection.reload
   .. automethod:: condoor.platforms.generic.Connection.send
   .. automethod:: condoor.platforms.generic.Connection.enable
   .. automethod:: condoor.platforms.generic.Connection.run_fsm

   .. autoattribute:: phase
   .. autoattribute:: condoor.Connection.family
   .. autoattribute:: condoor.Connection.platform
   .. autoattribute:: condoor.Connection.os_type
   .. autoattribute:: condoor.Connection.os_version
   .. autoattribute:: condoor.Connection.hostname
   .. autoattribute:: condoor.Connection.prompt
   .. autoattribute:: condoor.Connection.is_connected


   .. autoexception:: condoor.CommandTimeoutError
   .. autoexception:: condoor.TIMEOUT


Pexpect exceptions
------------------
Those are exceptions derived from pexpect module. This exception is used in FSM and :meth:`condoor.Connection.run_fsm`

