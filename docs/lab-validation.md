# Lab validation record

Run this on your selected device before recruiting participants. This release has
no physical robot, microphone/model or camera/model validation receipt. Preserve a
record for each robot + SDK + operating system + bridge + asset combination.

1. Record date, operator, framework commit, bridge/config hash, robot model/serial
   pseudonym, system/SDK/Python versions, ROS namespace, asset hashes and licenses.
2. Run GUI preflight. Verify device identity, capabilities, required assets and the
   receipt against the actual lab setup. Check that unselected devices remain closed.
3. Preview the selected camera/microphone. Verify no raw recording files appear.
   For perception, check a known frozen fixture and confirm dimensional head order.
4. Run a synthetic session: greeting/offer text, configured gesture and expression,
   a partial speech draft, correction, acceptance and final presentation. Compare
   the formal bid on screen, spoken text and canonical journal.
5. Disconnect during a presentation. Confirm the timeout is bounded, delivery is
   marked unknown, the conductor sees the error, and no replacement offer is made.
   Reconnect only for a new session. SDK completion does not prove human visibility.
6. Test withdrawal, deadline, explicit termination and application shutdown. Check
   device connections close and a second session has fresh input/model/history.
7. Export reports. Confirm offer utilities, arousal/valence, delivery flags and
   questionnaire targets match the records. Mark any protocol deviation/exclusion.

Record **pass/fail/not run** for each step with event IDs, configuration and outcome;
do not replace missing tests with an overall “supported” label. Store real lab
receipts locally, excluding participant recordings and identifiers from public Git.
