# =============================================================================
# delegators
#
# Copyright (c) 2016, Cisco Systems
# All rights reserved.
#
# # Author: Klaudiusz Staniek
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
# Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF
# THE POSSIBILITY OF SUCH DAMAGE.
# =============================================================================

from functools import partial


def delegate(attribute_name, method_names, attribute_names=()):
    """Passes the call to the attribute called attribute_name for
    every method listed in method_names.
    """
    # hack for python 2.7 as nonlocal is not available
    d = {
        'delegate': attribute_name,
        'methods': method_names,
        'attributes': attribute_names,
    }

    def setter(attribute, name, instance, value):
        setattr(getattr(instance, attribute), name, value)

    def getter(attribute, name, instance):
        return getattr(getattr(instance, attribute), name)

    def caller(attribute, name):
        return lambda self, *args, **kwargs: getter(attribute, name, self)(*args, **kwargs)

    def decorator(cls):
        delegate_name = d['delegate']
        if delegate_name.startswith("__"):
            delegate_name = "_" + cls.__name__ + delegate_name
        for name in d['methods']:
            setattr(cls, name, caller(delegate_name, name))
        for name in d['attributes']:
            setattr(cls, name, property(partial(getter, delegate_name, name), partial(setter, delegate_name, name)))
        return cls
    return decorator
