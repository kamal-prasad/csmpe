# =============================================================================
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

from unittest import TestCase, skip, skipIf

from csmpe.decorators import delegate


class Delegate():
    def __init__(self):
        self.attr1 = 1
        self.attr2 = 2

    def method1(self):
        return self.attr1

    def method2(self):
        return self.attr2

    def method3(self, arg1, arg2=None):
        return arg1, arg2

@delegate("delegate", ("method1", "method2", "method3"), ("attr1", "attr2",))
class DelegateTest(object):
    def __init__(self):
        self.delegate = Delegate()


class TestDelegateDecorator(TestCase):
    def test_method_delegate(self):
        dc = DelegateTest()

        self.assertEqual(dc.attr1, 1)
        self.assertEqual(dc.attr2, 2)
        self.assertEqual(dc.method1(), 1)
        self.assertEqual(dc.method2(), 2)

        dc.attr1 = 10
        dc.attr2 = 20

        self.assertEqual(dc.attr1, 10)
        self.assertEqual(dc.attr2, 20)

        self.assertEqual(dc.attr1, dc.delegate.attr1)
        self.assertEqual(dc.attr2, dc.delegate.attr2)

        self.assertEqual(dc.method3("10", arg2=20), ("10", 20))






