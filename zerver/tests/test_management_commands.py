# -*- coding: utf-8 -*-

import os
import glob
from datetime import timedelta
from mock import MagicMock, patch
from six.moves import map, filter
from typing import List, Dict, Any, Optional

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from zerver.lib.management import ZulipBaseCommand, CommandError
from zerver.lib.test_classes import ZulipTestCase
from zerver.lib.test_helpers import stdout_suppressed
from zerver.lib.test_runner import slow
from zerver.models import get_realm, UserProfile, Realm
from confirmation.models import RealmCreationKey, generate_realm_creation_url

class TestZulipBaseCommand(ZulipTestCase):
    def setUp(self):
        # type: () -> None
        self.zulip_realm = get_realm("zulip")
        self.command = ZulipBaseCommand()

    def test_get_realm(self):
        # type: () -> None
        self.assertEqual(self.command.get_realm(dict(realm_id='zulip')), self.zulip_realm)
        self.assertEqual(self.command.get_realm(dict(realm_id=None)), None)
        self.assertEqual(self.command.get_realm(dict(realm_id='1')), self.zulip_realm)
        with self.assertRaisesRegex(CommandError, "There is no realm with id"):
            self.command.get_realm(dict(realm_id='17'))
        with self.assertRaisesRegex(CommandError, "There is no realm with id"):
            self.command.get_realm(dict(realm_id='mit'))

    def test_get_user(self):
        # type: () -> None
        mit_realm = get_realm("zephyr")
        user_profile = self.example_user("hamlet")
        email = user_profile.email

        self.assertEqual(self.command.get_user(email, self.zulip_realm), user_profile)
        self.assertEqual(self.command.get_user(email, None), user_profile)

        error_message = "The realm '<Realm: zephyr 2>' does not contain a user with email"
        with self.assertRaisesRegex(CommandError, error_message):
            self.command.get_user(email, mit_realm)

        with self.assertRaisesRegex(CommandError, "server does not contain a user with email"):
            self.command.get_user('invalid_email@example.com', None)
        # TODO: Add a test for the MultipleObjectsReturned case once we make that possible.

    def get_users_sorted(self, options, realm):
        # type: (Dict[str, Any], Optional[Realm]) -> List[UserProfile]
        user_profiles = self.command.get_users(options, realm)
        return sorted(user_profiles, key = lambda x: x.email)

    def test_get_users(self):
        # type: () -> None
        user_emails = self.example_email("hamlet") + "," + self.example_email("iago")
        expected_user_profiles = [self.example_user("hamlet"), self.example_user("iago")]
        user_profiles = self.get_users_sorted(dict(users=user_emails), self.zulip_realm)
        self.assertEqual(user_profiles, expected_user_profiles)
        user_profiles = self.get_users_sorted(dict(users=user_emails), None)
        self.assertEqual(user_profiles, expected_user_profiles)

        user_emails = self.example_email("iago") + "," + self.mit_email("sipbtest")
        expected_user_profiles = [self.example_user("iago"), self.mit_user("sipbtest")]
        user_profiles = self.get_users_sorted(dict(users=user_emails), None)
        self.assertEqual(user_profiles, expected_user_profiles)
        error_message = "The realm '<Realm: zulip 1>' does not contain a user with email"
        with self.assertRaisesRegex(CommandError, error_message):
            self.command.get_users(dict(users=user_emails), self.zulip_realm)

        self.assertEqual(self.command.get_users(dict(users=self.example_email("iago")), self.zulip_realm),
                         [self.example_user("iago")])

        self.assertEqual(self.command.get_users(dict(users=None), None), [])

    def test_get_users_with_all_users_argument_enabled(self):
        # type: () -> None
        user_emails = self.example_email("hamlet") + "," + self.example_email("iago")
        expected_user_profiles = [self.example_user("hamlet"), self.example_user("iago")]
        user_profiles = self.get_users_sorted(dict(users=user_emails, all_users=False), self.zulip_realm)
        self.assertEqual(user_profiles, expected_user_profiles)
        error_message = "You can't use both -u/--users and -a/--all-users."
        with self.assertRaisesRegex(CommandError, error_message):
            self.command.get_users(dict(users=user_emails, all_users=True), None)

        expected_user_profiles = sorted(UserProfile.objects.filter(realm=self.zulip_realm),
                                        key = lambda x: x.email)
        user_profiles = self.get_users_sorted(dict(users=None, all_users=True), self.zulip_realm)
        self.assertEqual(user_profiles, expected_user_profiles)

        error_message = "You have to pass either -u/--users or -a/--all-users."
        with self.assertRaisesRegex(CommandError, error_message):
            self.command.get_users(dict(users=None, all_users=False), None)

        error_message = "The --all-users option requires a realm; please pass --realm."
        with self.assertRaisesRegex(CommandError, error_message):
            self.command.get_users(dict(users=None, all_users=True), None)

class TestCommandsCanStart(TestCase):

    def setUp(self):
        # type: () -> None
        self.commands = filter(
            lambda filename: filename != '__init__',
            map(
                lambda file: os.path.basename(file).replace('.py', ''),
                glob.iglob('*/management/commands/*.py')
            )
        )

    @slow("Aggregate of runs dozens of individual --help tests")
    def test_management_commands_show_help(self):
        # type: () -> None
        with stdout_suppressed() as stdout:
            for command in self.commands:
                print('Testing management command: {}'.format(command),
                      file=stdout)

                with self.assertRaises(SystemExit):
                    call_command(command, '--help')
        # zerver/management/commands/runtornado.py sets this to True;
        # we need to reset it here.  See #3685 for details.
        settings.RUNNING_INSIDE_TORNADO = False

class TestSendWebhookFixtureMessage(TestCase):
    COMMAND_NAME = 'send_webhook_fixture_message'

    def setUp(self):
        # type: () -> None
        self.fixture_path = os.path.join('some', 'fake', 'path.json')
        self.url = '/some/url/with/hook'

    @patch('zerver.management.commands.send_webhook_fixture_message.Command.print_help')
    def test_check_if_command_exits_when_fixture_param_is_empty(self, print_help_mock):
        # type: (MagicMock) -> None
        with self.assertRaises(SystemExit):
            call_command(self.COMMAND_NAME, url=self.url)

        print_help_mock.assert_any_call('./manage.py', self.COMMAND_NAME)

    @patch('zerver.management.commands.send_webhook_fixture_message.Command.print_help')
    def test_check_if_command_exits_when_url_param_is_empty(self, print_help_mock):
        # type: (MagicMock) -> None
        with self.assertRaises(SystemExit):
            call_command(self.COMMAND_NAME, fixture=self.fixture_path)

        print_help_mock.assert_any_call('./manage.py', self.COMMAND_NAME)

    @patch('zerver.management.commands.send_webhook_fixture_message.os.path.exists')
    def test_check_if_command_exits_when_fixture_path_does_not_exist(self, os_path_exists_mock):
        # type: (MagicMock) -> None
        os_path_exists_mock.return_value = False

        with self.assertRaises(SystemExit):
            call_command(self.COMMAND_NAME, fixture=self.fixture_path, url=self.url)

        os_path_exists_mock.assert_any_call(os.path.join(settings.DEPLOY_ROOT, self.fixture_path))

    @patch('zerver.management.commands.send_webhook_fixture_message.os.path.exists')
    @patch('zerver.management.commands.send_webhook_fixture_message.Client')
    @patch('zerver.management.commands.send_webhook_fixture_message.ujson')
    @patch("zerver.management.commands.send_webhook_fixture_message.open", create=True)
    def test_check_if_command_post_request_to_url_with_fixture(self,
                                                               open_mock,
                                                               ujson_mock,
                                                               client_mock,
                                                               os_path_exists_mock):
        # type: (MagicMock, MagicMock, MagicMock, MagicMock) -> None
        ujson_mock.loads.return_value = '{}'
        ujson_mock.dumps.return_value = {}
        os_path_exists_mock.return_value = True

        client = client_mock()

        call_command(self.COMMAND_NAME, fixture=self.fixture_path, url=self.url)
        self.assertTrue(ujson_mock.dumps.called)
        self.assertTrue(ujson_mock.loads.called)
        self.assertTrue(open_mock.called)
        client.post.assert_called_once_with(self.url, {}, content_type="application/json")

class TestGenerateRealmCreationLink(ZulipTestCase):
    COMMAND_NAME = "generate_realm_creation_link"

    def test_generate_link_and_create_realm(self):
        # type: () -> None
        email = "user1@test.com"
        generated_link = generate_realm_creation_url()

        with self.settings(OPEN_REALM_CREATION=False):
            # Check realm creation page is accessible
            result = self.client_get(generated_link)
            self.assert_in_success_response([u"Create a new Zulip organization"], result)

            # Create Realm with generated link
            self.assertIsNone(get_realm('test'))
            result = self.client_post(generated_link, {'email': email})
            self.assertEqual(result.status_code, 302)
            self.assertTrue(result["Location"].endswith(
                "/accounts/send_confirm/%s" % (email,)))
            result = self.client_get(result["Location"])
            self.assert_in_response("Check your email so we can get started.", result)

            # Generated link used for creating realm
            result = self.client_get(generated_link)
            self.assert_in_success_response(["The organization creation link has expired or is not valid."], result)

    def test_realm_creation_with_random_link(self):
        # type: () -> None
        with self.settings(OPEN_REALM_CREATION=False):
            # Realm creation attempt with an invalid link should fail
            random_link = "/create_realm/5e89081eb13984e0f3b130bf7a4121d153f1614b"
            result = self.client_get(random_link)
            self.assert_in_success_response(["The organization creation link has expired or is not valid."], result)

    def test_realm_creation_with_expired_link(self):
        # type: () -> None
        with self.settings(OPEN_REALM_CREATION=False):
            generated_link = generate_realm_creation_url()
            key = generated_link[-24:]
            # Manually expire the link by changing the date of creation
            obj = RealmCreationKey.objects.get(creation_key=key)
            obj.date_created = obj.date_created - timedelta(days=settings.REALM_CREATION_LINK_VALIDITY_DAYS + 1)
            obj.save()

            result = self.client_get(generated_link)
            self.assert_in_success_response(["The organization creation link has expired or is not valid."], result)
