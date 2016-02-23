The Plugin Structure
====================

The the plugin code may inherit from CSMPlugin class. This is not mandatory, however the plugin code MUST
be able to accept the PluginContext object in the constructor as a paramter
and have minimum four attributes:

 - name
 - phases
 - platforms
 - os


.. automodule:: csmpe

CSMPlugin Class
---------------

.. autoclass:: CSMPlugin

    :members: __init__, run, platforms

    .. autoattribute:: name
    .. autoattribute:: phases
    .. autoattribute:: platforms
    .. autoattribute:: os
