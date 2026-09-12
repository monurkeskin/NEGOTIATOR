"""Run this file with the robot's Python 2.7/NAOqi 2.5 SDK, outside the core env."""
from __future__ import print_function

import argparse
import platform

try:
    from .protocol import serve
except (ImportError, ValueError):
    from protocol import serve


class NaoqiDevice:
    def __init__(self, host, port, family):
        self.host, self.port, self.family = host, port, family
        self.tts = self.behaviors = self.system = None

    def call(self, operation, payload):
        if operation == 'hello':
            if platform.python_version_tuple()[:2] != ('2', '7'):
                raise RuntimeError('This bridge requires the separate Python 2.7 NAOqi SDK runtime.')
            from naoqi import ALProxy
            self.system = ALProxy('ALSystem', self.host, self.port)
            self.tts = ALProxy('ALTextToSpeech', self.host, self.port)
            self.behaviors = ALProxy('ALBehaviorManager', self.host, self.port)
            return {'family': self.family, 'runtime': self.system.systemVersion(),
                    'python': platform.python_version(), 'capabilities': ['speech', 'gesture'],
                    'assets': list(self.behaviors.getInstalledBehaviors()),
                    'hardware_tested': False, 'family_source': 'operator_configuration'}
        if operation != 'present' or self.tts is None:
            raise ValueError('Preflight is required; operation must be present.')
        if payload.get('face'):
            raise ValueError('A face display is not supported by the NAOqi bridge.')
        gesture = payload.get('gesture')
        if gesture:
            if not self.behaviors.isBehaviorInstalled(gesture):
                raise ValueError('Configured gesture is not installed.')
            self.behaviors.runBehavior(gesture)
        # Canonical text is literal: do not interpret inline NAOqi control sequences.
        text = payload['text'].replace('\\', ' ')
        self.tts.say(text.encode('utf-8'))
        return {'delivered': True, 'acknowledgement': 'NAOqi calls returned'}

    def close(self):
        # Do not stop unrelated lab behaviors or change autonomous-life settings.
        self.tts = self.behaviors = self.system = None


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', type=int, default=9559)
    parser.add_argument('--family', choices=['nao', 'pepper'], required=True)
    options = parser.parse_args()
    serve(NaoqiDevice(options.host, options.port, options.family))
