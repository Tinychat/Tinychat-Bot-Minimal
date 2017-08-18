# -*- coding: utf-8 -*-
import logging
import re
import threading
import pinylib
from apis import other, locals_
from page import privacy

__version__ = '1.0.2'
log = logging.getLogger(__name__)


class TinychatBot(pinylib.TinychatRTMPClient):
    privacy_settings = None
    is_broadcasting = False

    def on_join(self, join_info):
        """ Application message received when a user joins the room.
        :param join_info: Information about the user joining.
        :type join_info: dict
        """
        log.info('user join info: %s' % join_info)
        _user = self.users.add(join_info)
        if _user is not None:
            if _user.account:
                tc_info = pinylib.apis.tinychat.user_info(_user.account)
                if tc_info is not None:
                    _user.tinychat_id = tc_info
                    _user.last_login = tc_info['last_active']
                if _user.is_owner:
                    _user.user_level = 1
                    self.console_write(pinylib.COLOR['red'], 'Room Owner %s:%d:%s' %
                                       (_user.nick, _user.id, _user.account))
                elif _user.is_mod:
                    _user.user_level = 3
                    self.console_write(pinylib.COLOR['bright_red'], 'Moderator %s:%d:%s' %
                                       (_user.nick, _user.id, _user.account))
                else:
                    self.console_write(pinylib.COLOR['bright_yellow'], '%s:%d has account: %s' %
                                       (_user.nick, _user.id, _user.account))

                    if _user.account in pinylib.CONFIG.B_ACCOUNT_BANS:
                        if self.is_client_mod:
                            self.send_ban_msg(_user.nick, _user.id)
                            if pinylib.CONFIG.B_FORGIVE_AUTO_BANS:
                                self.send_forgive_msg(_user.id)
                            self.send_bot_msg('*Auto-Banned:* (bad account)')

            else:
                if _user.id is not self._client_id:
                    if _user.lf and not pinylib.CONFIG.B_ALLOW_LURKERS and self.is_client_mod:
                        self.send_ban_msg(_user.nick, _user.id)
                        if pinylib.CONFIG.B_FORGIVE_AUTO_BANS:
                            self.send_forgive_msg(_user.id)
                        self.send_bot_msg('*Auto-Banned:* (lurkers not allowed)')
                    elif not pinylib.CONFIG.B_ALLOW_GUESTS and self.is_client_mod:
                        self.send_ban_msg(_user.nick, _user.id)
                        if pinylib.CONFIG.B_FORGIVE_AUTO_BANS:
                            self.send_forgive_msg(_user.id)
                        self.send_bot_msg('*Auto-Banned:* (guests not allowed)')
                    else:
                        self.console_write(pinylib.COLOR['cyan'], '%s:%d joined the room.' % (_user.nick, _user.id))

    def on_joinsdone(self):
        """ Application message received when all room users information have been received. """
        if self.is_client_mod:
            self.send_banlist_msg()
            self.load_list(nicks=True, accounts=True, strings=True)
        if self.is_client_owner and self.param.roomtype != 'default':
            threading.Thread(target=self.get_privacy_settings).start()

    def on_avon(self, uid, name, greenroom=False):
        """ Application message received when a user starts broadcasting.

        :param uid: The Id of the user.
        :type uid: str
        :param name: The nick name of the user.
        :type name: str
        :param greenroom: True the user is waiting in the greenroom.
        :type greenroom: bool
        """
        if greenroom:
            _user = self.users.search_by_id(name)
            if _user is not None:
                _user.is_waiting = True
                self.send_bot_msg('%s:%s *is waiting in the greenroom.*' % (_user.nick, _user.id))
        else:
            _user = self.users.search(name)
            if _user is not None and _user.is_waiting:
                _user.is_waiting = False
            if not pinylib.CONFIG.B_ALLOW_BROADCASTS and self.is_client_mod:
                self.send_close_user_msg(name)
                self.console_write(pinylib.COLOR['cyan'], 'Auto closed broadcast %s:%s' % (name, uid))
            else:
                self.console_write(pinylib.COLOR['cyan'], '%s:%s is broadcasting.' % (name, uid))

    def on_nick(self, old, new, uid):
        """ Application message received when a user changes nick name.

        :param old: The old nick name of the user.
        :type old: str
        :param new: The new nick name of the user
        :type new: str
        :param uid: The Id of the user.
        :type uid: int
        """
        if uid == self._client_id:
            self.nickname = new
        old_info = self.users.search(old)
        old_info.nick = new
        if not self.users.change(old, new, old_info):
            log.error('failed to change nick for user: %s' % new)
        if self.check_nick(old, old_info):
            if pinylib.CONFIG.B_FORGIVE_AUTO_BANS:
                self.send_forgive_msg(uid)
        elif uid != self._client_id:
            if self.is_client_mod and pinylib.CONFIG.B_GREET:
                if old_info.account:
                    self.send_bot_msg('*Greetings & Welcome to ' + self.roomname + '* %s: %s (%s)' %
                                      (new, old_info.account, uid))
                else:
                    self.send_bot_msg('*Greetings & Welcome to ' + self.roomname + '* - ' + new)

        self.console_write(pinylib.COLOR['bright_cyan'], '%s:%s changed nick to: %s' % (old, uid, new))

    # Message Method.
    def send_bot_msg(self, msg, use_chat_msg=False):
        """ Send a chat message to the room.

        NOTE: If the client is moderator, send_owner_run_msg will be used.
        If the client is not a moderator, send_chat_msg will be used.
        Setting use_chat_msg to True, forces send_chat_msg to be used.

        :param msg: The message to send.
        :type msg: str
        :param use_chat_msg: True, use normal chat messages,
        False, send messages depending on weather or not the client is mod.
        :type use_chat_msg: bool
        """
        if use_chat_msg:
            self.send_chat_msg(msg)
        else:
            if self.is_client_mod:
                self.send_owner_run_msg(msg)
            else:
                self.send_chat_msg(msg)

    # Command Handler.
    def message_handler(self, decoded_msg):
        """ Message handler.

        :param decoded_msg: The decoded msg(text).
        :type decoded_msg: str
        """
        prefix = pinylib.CONFIG.B_PREFIX
        if decoded_msg.startswith(prefix):
            parts = decoded_msg.split(' ')
            cmd = parts[0].lower().strip()
            cmd_arg = ' '.join(parts[1:]).strip()
            # Always enabled to allow contact with the bot even when public commands are disabled.
            if self.has_level(5):
                if cmd == prefix + 'pmme':
                    self.do_pmme()

                elif cmd == prefix + 'fullscreen':
                    self.do_full_screen()

            # Public commands. (if enabled)
            if (pinylib.CONFIG.B_PUBLIC_CMD and self.has_level(5)) or self.active_user.user_level < 5:
                if cmd == prefix + 'who?':
                    self.do_who_plays()

                elif cmd == prefix + 'help':
                    self.do_help()

                elif cmd == prefix + 'uptime':
                    self.do_uptime()

                # Tinychat API commands.
                elif cmd == prefix + 'spy':
                    threading.Thread(target=self.do_spy, args=(cmd_arg,)).start()

                elif cmd == prefix + 'spyuser':
                    threading.Thread(target=self.do_account_spy, args=(cmd_arg,)).start()

                elif cmd == prefix + 'room':
                    threading.Thread(target=self.do_room_info, args=(cmd_arg,)).start()

                # Other API commands.
                elif cmd == prefix + 'urban':
                    threading.Thread(target=self.do_search_urban_dictionary, args=(cmd_arg,)).start()

                elif cmd == prefix + 'ip':
                    threading.Thread(target=self.do_whois_ip, args=(cmd_arg,)).start()

                elif cmd == prefix + 'time':
                    threading.Thread(target=self.do_time, args=(cmd_arg,)).start()

                elif cmd == prefix + 'translate':
                    threading.Thread(target=self.do_translate, args=(cmd_arg,)).start()

                elif cmd == prefix + 'advice':
                    threading.Thread(target=self.do_advice).start()

                elif cmd == prefix + 'chuck':
                    threading.Thread(target=self.do_chuck_norris).start()

                elif cmd == prefix + '8ball':
                    self.do_8ball(cmd_arg)

                elif cmd == prefix + 'roll':
                    self.do_dice()

                elif cmd == prefix + 'flip':
                    self.do_flip_coin()

            # Print command to console.
            self.console_write(pinylib.COLOR['yellow'], self.active_user.nick + ': ' + cmd + ' ' + cmd_arg)
        else:
            #  Print chat message to console.
            self.console_write(pinylib.COLOR['green'], self.active_user.nick + ': ' + decoded_msg)
            # Only check chat msg for ban string if we are mod.
            if self.is_client_mod and self.active_user.user_level > 4:
                threading.Thread(target=self.check_msg, args=(decoded_msg,)).start()

        self.active_user.last_msg = decoded_msg

    def do_make_mod(self, account):
        """ Make a tinychat account a room moderator.

        :param account: The account to make a moderator.
        :type account: str
        """
        if self.is_client_owner:
            if len(account) is 0:
                self.send_private_msg('Missing account name.', self.active_user.nick)
            else:
                tc_user = self.privacy_settings.make_moderator(account)
                if tc_user is None:
                    self.send_private_msg('*The account is invalid.*', self.active_user.nick)
                elif not tc_user:
                    self.send_private_msg('*%s* is already a moderator.' % account, self.active_user.nick)
                elif tc_user:
                    self.send_private_msg('*%s* was made a room moderator.' % account, self.active_user.nick)

    def do_remove_mod(self, account):
        """ Removes a tinychat account from the moderator list.

        :param account: The account to remove from the moderator list.
        :type account: str
        """
        if self.is_client_owner:
            if len(account) is 0:
                self.send_private_msg('Missing account name.', self.active_user.nick)
            else:
                tc_user = self.privacy_settings.remove_moderator(account)
                if tc_user:
                    self.send_private_msg('*%s* is no longer a room moderator.' % account, self.active_user.nick)
                elif not tc_user:
                    self.send_private_msg('*%s* is not a room moderator.' % account, self.active_user.nick)

    def do_directory(self):
        """ Toggles if the room should be shown on the directory. """
        if self.is_client_owner:
            if self.privacy_settings.show_on_directory():
                self.send_private_msg('*Room IS shown on the directory.*', self.active_user.nick)
            else:
                self.send_private_msg('*Room is NOT shown on the directory.*', self.active_user.nick)

    def do_push2talk(self):
        """ Toggles if the room should be in push2talk mode. """
        if self.is_client_owner:
            if self.privacy_settings.set_push2talk():
                self.send_private_msg('*Push2Talk is enabled.*', self.active_user.nick)
            else:
                self.send_private_msg('*Push2Talk is disabled.*', self.active_user.nick)

    def do_green_room(self):
        """ Toggles if the room should be in greenroom mode. """
        if self.is_client_owner:
            if self.privacy_settings.set_greenroom():
                self.send_private_msg('*Green room is enabled.*', self.active_user.nick)
            else:
                self.send_private_msg('*Green room is disabled.*', self.active_user.nick)

    def do_clear_room_bans(self):
        """ Clear all room bans. """
        if self.is_client_owner:
            if self.privacy_settings.clear_bans():
                self.send_private_msg('*All room bans was cleared.*', self.active_user.nick)

    def do_kill(self):
        """ Kills the bot. """
        self.disconnect()
        if self.is_green_connected:
            self.disconnect(greenroom=True)

    def do_reboot(self):
        """ Reboots the bot. """
        if self.is_green_connected:
            self.disconnect(greenroom=True)
        self.reconnect()

    def do_op_user(self, user_name):
        """ Lets the room owner, a mod or a bot controller make another user a bot controller.

        :param user_name: The user to op.
        :type user_name: str
        """
        if self.is_client_mod:
            if len(user_name) is 0:
                self.send_bot_msg('Missing username.')
            else:
                _user = self.users.search(user_name)
                if _user is not None:
                    _user.user_level = 4
                    self.send_private_msg('*%s* is now a bot controller' % user_name, self.active_user.nick)
                    self.send_private_msg('You are now a bot controller (Level 4).', user_name)
                    self.send_private_msg('Commands https://github.com/Tinychat/Tinychat-Bot/wiki#level-4', user_name)
                else:
                    self.send_private_msg('No user named: %s' % user_name, self.active_user.nick)

    def do_deop_user(self, user_name):
        """ Lets the room owner, a mod or a bot controller remove a user from being a bot controller.

        :param user_name: The user to deop.
        :type user_name: str
        """
        if self.is_client_mod:
            if len(user_name) is 0:
                self.send_private_msg('Missing username.', self.active_user.nick)
            else:
                _user = self.users.search(user_name)
                if _user is not None:
                    _user.user_level = 5
                    self.send_private_msg('*%s* was removed' % user_name, self.active_user.nick)
                else:
                    self.send_private_msg('No user named: %s' % user_name, self.active_user.nick)

    def do_cam_up(self):
        """ Makes the bot cam up. """
        if not self.is_broadcasting:
            self.send_bauth_msg()
            self.connection.createstream()
            self.is_broadcasting = True

    def do_cam_down(self):
        """ Makes the bot cam down. """
        if self.is_broadcasting:
            self.connection.closestream()
            self.is_broadcasting = False

    def do_nocam(self):
        """ Toggles if broadcasting is allowed or not. """
        pinylib.CONFIG.B_ALLOW_BROADCASTS = not pinylib.CONFIG.B_ALLOW_BROADCASTS
        self.send_private_msg('*Allow Broadcasts:* %s' % pinylib.CONFIG.B_ALLOW_BROADCASTS, self.active_user.nick)

    def do_guests(self):
        """ Toggles if guests are allowed to join the room or not. """
        pinylib.CONFIG.B_ALLOW_GUESTS = not pinylib.CONFIG.B_ALLOW_GUESTS
        self.send_private_msg('*Allow Guests:* %s' % pinylib.CONFIG.B_ALLOW_GUESTS, self.active_user.nick)

    def do_lurkers(self):
        """ Toggles if lurkers are allowed or not. """
        pinylib.CONFIG.B_ALLOW_LURKERS = not pinylib.CONFIG.B_ALLOW_LURKERS
        self.send_private_msg('*Allow Lurkers:* %s' % pinylib.CONFIG.B_ALLOW_LURKERS, self.active_user.nick)

    def do_guest_nicks(self):
        """ Toggles if guest nicks are allowed or not. """
        pinylib.CONFIG.B_ALLOW_GUESTS_NICKS = not pinylib.CONFIG.B_ALLOW_GUESTS_NICKS
        self.send_private_msg('*Allow Guest Nicks:* %s' % pinylib.CONFIG.B_ALLOW_GUESTS_NICKS, self.active_user.nick)

    def do_newusers(self):
        """ Toggles if newusers are allowed to join the room or not. """
        pinylib.CONFIG.B_ALLOW_NEWUSERS = not pinylib.CONFIG.B_ALLOW_NEWUSERS
        self.send_private_msg('*Allow Newusers:* %s' % pinylib.CONFIG.B_ALLOW_NEWUSERS, self.active_user.nick)

    def do_greet(self):
        """ Toggles if users should be greeted on entry. """
        pinylib.CONFIG.B_GREET = not pinylib.CONFIG.B_GREET
        self.send_private_msg('*Greet Users:* %s' % pinylib.CONFIG.B_GREET, self.active_user.nick)

    def do_public_cmds(self):
        """ Toggles if public commands are public or not. """
        pinylib.CONFIG.B_PUBLIC_CMD = not pinylib.CONFIG.B_PUBLIC_CMD
        self.send_private_msg('*Public Commands Enabled:* %s' % pinylib.CONFIG.B_PUBLIC_CMD, self.active_user.nick)

    def do_room_settings(self):
        """ Shows current room settings. """
        if self.is_client_owner:
            settings = self.privacy_settings.current_settings()
            self.send_private_msg('*Broadcast Password:* %s' % settings['broadcast_pass'], self.active_user.nick)
            self.send_private_msg('*Room Password:* %s' % settings['room_pass'], self.active_user.nick)
            self.send_private_msg('*Login Type:* %s' % settings['allow_guest'], self.active_user.nick)
            self.send_private_msg('*Directory:* %s' % settings['show_on_directory'], self.active_user.nick)
            self.send_private_msg('*Push2Talk:* %s' % settings['push2talk'], self.active_user.nick)
            self.send_private_msg('*Greenroom:* %s' % settings['greenroom'], self.active_user.nick)

    def do_close_broadcast(self, user_name):
        """ Close a user broadcasting.

        :param user_name: The username to close.
        :type user_name: str
        """
        if self.is_client_mod:
            if len(user_name) is 0:
                self.send_private_msg('Missing username.', self.active_user.nick)
            else:
                if self.users.search(user_name) is not None:
                    self.send_close_user_msg(user_name)
                else:
                    self.send_private_msg('No user named: ' + user_name, self.active_user.nick)

    def do_clear(self):
        """ Clears the chat box. """
        if self.is_client_mod:
            for x in range(0, 10):
                self.send_owner_run_msg(' ')
        else:
            clear = '133,133,133,133,133,133,133,133,133,133,133,133,133,133,133'
            self.connection.call('privmsg', [clear, u'#262626,en'])

    def do_nick(self, new_nick):
        """ Set a new nick for the bot.

        :param new_nick: The new nick name.
        :type new_nick: str
        """
        if len(new_nick) is 0:
            self.nickname = pinylib.string_util.create_random_string(5, 25)
            self.set_nick()
        else:
            if re.match('^[][{}a-zA-Z0-9_]{1,25}$', new_nick):
                self.nickname = new_nick
                self.set_nick()

    def do_topic(self, topic):
        """ Sets the room topic.

        :param topic: Sets a topic for the room.
        :type topic: str
        """
        if self.is_client_mod:
            if len(topic) is 0:
                self.send_topic_msg('')
                self.send_private_msg('Topic was cleared.', self.active_user.nick)
            else:
                self.send_topic_msg(topic)
                self.send_private_msg('The room topic was set to: ' + topic, self.active_user.nick)

    def do_kick(self, user_name):
        """ Kick a user out of the room.

        :param user_name: The username to kick.
        :type user_name: str
        """
        if self.is_client_mod:
            if len(user_name) is 0:
                self.send_private_msg('Missing username.', self.active_user.nick)
            elif user_name == self.nickname:
                self.send_private_msg('Action not allowed.', self.active_user.nick)
            else:
                if user_name.startswith('*'):
                    user_name = user_name.replace('*', '')
                    _users = self.users.search_containing(user_name)
                    if len(_users) > 0:
                        for i, user in enumerate(_users):
                            if user.nick != self.nickname and user.user_level > self.active_user.user_level:
                                if i <= pinylib.CONFIG.B_MAX_MATCH_BANS - 1:
                                    self.send_ban_msg(user.nick, user.id)
                                    a = pinylib.string_util.random.uniform(0.0, 1.0)
                                    pinylib.time.sleep(a)
                                    self.send_forgive_msg(user.id)
                                    pinylib.time.sleep(0.5)
                else:
                    _user = self.users.search(user_name)
                    if _user is None:
                        self.send_private_msg('No user named: *%s*' % user_name, self.active_user.nick)
                    elif _user.user_level < self.active_user.user_level:
                        self.send_private_msg('Not allowed.', self.active_user.nick)
                    else:
                        self.send_ban_msg(user_name, _user.id)
                        self.send_forgive_msg(_user.id)

    def do_ban(self, user_name):
        """ Ban a user from the room.

        :param user_name: The username to ban.
        :type user_name: str
        """
        if self.is_client_mod:
            if len(user_name) is 0:
                self.send_private_msg('Missing username.', self.active_user.nick)
            elif user_name == self.nickname:
                self.send_private_msg('Action not allowed.', self.active_user.nick)
            else:
                if user_name.startswith('*'):
                    user_name = user_name.replace('*', '')
                    _users = self.users.search_containing(user_name)
                    if len(_users) > 0:
                        for i, user in enumerate(_users):
                            if user.nick != self.nickname and user.user_level > self.active_user.user_level:
                                if i <= pinylib.CONFIG.B_MAX_MATCH_BANS - 1:
                                    self.send_ban_msg(user.nick, user.id)
                                    a = pinylib.string_util.random.uniform(0.0, 1.5)
                                    pinylib.time.sleep(a)
                else:
                    _user = self.users.search(user_name)
                    if _user is None:
                        self.send_private_msg('No user named: *%s*' % user_name, self.active_user.nick)
                    elif _user.user_level < self.active_user.user_level:
                        self.send_private_msg('Not allowed.', self.active_user.nick)
                    else:
                        self.send_ban_msg(user_name, _user.id)

    def do_bad_nick(self, bad_nick):
        """ Adds a username to the nick bans file.

        :param bad_nick: The bad nick to write to the nick bans file.
        :type bad_nick: str
        """
        if self.is_client_mod:
            if len(bad_nick) is 0:
                self.send_bot_msg('Missing username.')
            elif bad_nick in pinylib.CONFIG.B_NICK_BANS:
                self.send_private_msg('*%s* is already in list.' % bad_nick, self.active_user.nick)
            else:
                pinylib.file_handler.file_writer(self.config_path(),
                                                 pinylib.CONFIG.B_NICK_BANS_FILE_NAME, bad_nick)
                self.send_private_msg('*%s* was added to file.' % bad_nick, self.active_user.nick)
                self.load_list(nicks=True)

    def do_remove_bad_nick(self, bad_nick):
        """ Removes nick from the nick bans file.

        :param bad_nick: The bad nick to remove from the nick bans file.
        :type bad_nick: str
        """
        if self.is_client_mod:
            if len(bad_nick) is 0:
                self.send_private_msg('Missing username', self.active_user.nick)
            else:
                if bad_nick in pinylib.CONFIG.B_NICK_BANS:
                    rem = pinylib.file_handler.remove_from_file(self.config_path(),
                                                                pinylib.CONFIG.B_NICK_BANS_FILE_NAME, bad_nick)
                    if rem:
                        self.send_private_msg('*%s* was removed.' % bad_nick, self.active_user.nick)
                        self.load_list(nicks=True)

    def do_bad_string(self, bad_string):
        """ Adds a string to the string bans file.

        :param bad_string: The bad string to add to the string bans file.
        :type bad_string: str
        """
        if self.is_client_mod:
            if len(bad_string) is 0:
                self.send_private_msg('Ban string can\'t be blank.', self.active_user.nick)
            elif len(bad_string) < 3:
                self.send_private_msg('Ban string to short: ' + str(len(bad_string)), self.active_user.nick)
            elif bad_string in pinylib.CONFIG.B_STRING_BANS:
                self.send_private_msg('*%s* is already in list.' % bad_string, self.active_user.nick)
            else:
                pinylib.file_handler.file_writer(self.config_path(),
                                                 pinylib.CONFIG.B_STRING_BANS_FILE_NAME, bad_string)
                self.send_private_msg('*%s* was added to file.' % bad_string, self.active_user.nick)
                self.load_list(strings=True)

    def do_remove_bad_string(self, bad_string):
        """ Removes a string from the string bans file.

        :param bad_string: The bad string to remove from the string bans file.
        :type bad_string: str
        """
        if self.is_client_mod:
            if len(bad_string) is 0:
                self.send_private_msg('Missing word string.', self.active_user.nick)
            else:
                if bad_string in pinylib.CONFIG.B_STRING_BANS:
                    rem = pinylib.file_handler.remove_from_file(self.config_path(),
                                                                pinylib.CONFIG.B_STRING_BANS_FILE_NAME, bad_string)
                    if rem:
                        self.send_private_msg('*%s* was removed.' % bad_string, self.active_user.nick)
                        self.load_list(strings=True)

    def do_bad_account(self, bad_account_name):
        """ Adds an account name to the account bans file.

        :param bad_account_name: The bad account name to add to the account bans file.
        :type bad_account_name: str
        """
        if self.is_client_mod:
            if len(bad_account_name) is 0:
                self.send_private_msg('Account can\'t be blank.', self.active_user.nick)
            elif len(bad_account_name) < 3:
                self.send_private_msg('Account to short: ' + str(len(bad_account_name)), self.active_user.nick)
            elif bad_account_name in pinylib.CONFIG.B_ACCOUNT_BANS:
                self.send_private_msg('%s is already in list.' % bad_account_name, self.active_user.nick)
            else:
                pinylib.file_handler.file_writer(self.config_path(),
                                                 pinylib.CONFIG.B_ACCOUNT_BANS_FILE_NAME, bad_account_name)
                self.send_private_msg('*%s* was added to file.' % bad_account_name, self.active_user.nick)
                self.load_list(accounts=True)

    def do_remove_bad_account(self, bad_account):
        """ Removes an account from the account bans file.

        :param bad_account: The bad account name to remove from account bans file.
        :type bad_account: str
        """
        if self.is_client_mod:
            if len(bad_account) is 0:
                self.send_private_msg('Missing account.', self.active_user.nick)
            else:
                if bad_account in pinylib.CONFIG.B_ACCOUNT_BANS:
                    rem = pinylib.file_handler.remove_from_file(self.config_path(),
                                                                pinylib.CONFIG.B_ACCOUNT_BANS_FILE_NAME, bad_account)
                    if rem:
                        self.send_private_msg('*%s* was removed.' % bad_account, self.active_user.nick)
                        self.load_list(accounts=True)

    def do_list_info(self, list_type):
        """ Shows info of different lists/files.

        :param list_type: The type of list to find info for.
        :type list_type: str
        """
        if self.is_client_mod:
            if len(list_type) is 0:
                self.send_private_msg('Missing list type.', self.active_user.nick)
            else:
                if list_type.lower() == 'nicks':
                    if len(pinylib.CONFIG.B_NICK_BANS) is 0:
                        self.send_private_msg('No items in this list.', self.active_user.nick)
                    else:
                        self.send_private_msg('%s *nicks bans in list.*' % len(pinylib.CONFIG.B_NICK_BANS),
                                              self.active_user.nick)

                elif list_type.lower() == 'words':
                    if len(pinylib.CONFIG.B_STRING_BANS) is 0:
                        self.send_private_msg('No items in this list.', self.active_user.nick)
                    else:
                        self.send_private_msg('%s *string bans in list.*' % pinylib.CONFIG.B_STRING_BANS,
                                              self.active_user.nick)

                elif list_type.lower() == 'accounts':
                    if len(pinylib.CONFIG.B_ACCOUNT_BANS) is 0:
                        self.send_private_msg('No items in this list.', self.active_user.nick)
                    else:
                        self.send_private_msg('%s *account bans in list.*' % pinylib.CONFIG.B_ACCOUNT_BANS,
                                              self.active_user.nick)

                elif list_type.lower() == 'mods':
                    if self.is_client_owner:
                        if len(self.privacy_settings.room_moderators) is 0:
                            self.send_private_msg('*There is currently no moderators for this room.*',
                                                  self.active_user.nick)
                        elif len(self.privacy_settings.room_moderators) is not 0:
                            mods = ', '.join(self.privacy_settings.room_moderators)
                            self.send_private_msg('*Moderators:* ' + mods, self.active_user.nick)

    def do_user_info(self, user_name):
        """ Shows user object info for a given user name.

        :param user_name: The user name of the user to show the info for.
        :type user_name: str
        """
        if self.is_client_mod:
            if len(user_name) is 0:
                self.send_private_msg('Missing username.', self.active_user.nick)
            else:
                _user = self.users.search(user_name)
                if _user is None:
                    self.send_private_msg('No user named: %s' % user_name, self.active_user.nick)
                else:
                    if _user.account and _user.tinychat_id is None:
                        user_info = pinylib.apis.tinychat.user_info(_user.account)
                        if user_info is not None:
                            _user.tinychat_id = user_info['tinychat_id']
                            _user.last_login = user_info['last_active']
                    self.send_private_msg('*User Level:* %s' % _user.user_level, self.active_user.nick)
                    online_time = (pinylib.time.time() - _user.join_time) * 1000
                    self.send_private_msg('*Online Time:* %s' % self.format_time(online_time), self.active_user.nick)

                    if _user.tinychat_id is not None:
                        self.send_private_msg('*Account:* ' + str(_user.account), self.active_user.nick)
                        self.send_private_msg('*Tinychat ID:* ' + str(_user.tinychat_id), self.active_user.nick)
                        self.send_private_msg('*Last login:* ' + str(_user.last_login), self.active_user.nick)
                    self.send_private_msg('*Last message:* ' + str(_user.last_msg), self.active_user.nick)

    # == Public Command Methods. ==
    def do_full_screen(self):
        """ Post a full screen link."""
        self.send_bot_msg('https://www.ruddernation.info/' + self.roomname)

    def do_help(self):
        """ Posts a link to github readme/wiki or other page about the bot commands. """
        self.send_undercover_msg(self.active_user.nick,
                                 '*Commands:* https://github.com/Tinychat/Tinychat-Bot-Minimal/wiki')

    def do_uptime(self):
        """ Shows the bots uptime. """
        self.send_bot_msg('*Uptime:* ' + self.format_time(self.get_runtime()))

    def do_pmme(self):
        """ Opens a PM session with the bot. """
        self.send_private_msg('How can i help you *' + self.active_user.nick + '*?', self.active_user.nick)

    def do_cam_approve(self, user_name):
        """ Send a cam approve message to a user.

        :param user_name: The nick name of the user to allow broadcast for.
        :type user_name: str
        """
        if self.is_client_mod and self.param.is_greenroom:
            if len(user_name) is 0 and self.active_user.is_waiting:
                self.active_user.is_waiting = False
                self.send_cam_approve_msg(self.active_user.nick, self.active_user.id)

            elif len(user_name) > 0:
                _user = self.users.search(user_name)
                if _user is not None and _user.is_waiting:
                    _user.is_waiting = False
                    self.send_cam_approve_msg(_user.nick, _user.id)
                else:
                    self.send_private_msg('No user named: %s' % user_name, self.active_user.nick)

    # == Tinychat API Command Methods. ==
    def do_spy(self, roomname):
        """ Shows info for a given room.

        :param roomname: The room name to find spy info for.
        :type roomname: str
        """
        if self.is_client_mod:
            if len(roomname) is 0:
                self.send_undercover_msg(self.active_user.nick, 'Missing room name.')
            else:
                spy_info = pinylib.apis.tinychat.spy_info(roomname)
                if spy_info is None:
                    self.send_undercover_msg(self.active_user.nick, 'Failed to retrieve information.')
                elif 'error' in spy_info:
                    self.send_undercover_msg(self.active_user.nick, spy_info['error'])
                else:
                    self.send_bot_msg('*Mods:* %s, *Broadcasters:* %s, *Users:* %s' %
                                      (spy_info['mod_count'], spy_info['broadcaster_count'],
                                       spy_info['total_count']))
                    if self.has_level(3):
                        users = ', '.join(spy_info['users'])
                        self.send_undercover_msg(self.active_user.nick, '*' + users + '*')

    def do_account_spy(self, account):
        """
        Shows info about a tinychat account.
        :param account: str tinychat account.
        """
        if self.is_client_mod:
            if len(account) is 0:
                self.send_undercover_msg(self.active_user.nick, 'Missing username to search for.')
            else:
                tc_usr = pinylib.apis.tinychat.user_info(account)
                if tc_usr is None:
                    self.send_undercover_msg(self.active_user.nick, 'Could not find tinychat info for: ' + account)
                else:
                    self.send_bot_msg('*Account:* ' + '*' + account + '*')
                    self.send_bot_msg('*Website:* ' + tc_usr['website'])
                    self.send_bot_msg('*Bio:* ' + tc_usr['biography'])
                    self.send_bot_msg('*Location:* ' + tc_usr['location'])
                    self.send_bot_msg('*Last login:* ' + tc_usr['last_active'])
                    self.send_bot_msg('*Room ID:* ' + tc_usr['tinychat_id'])

    def do_room_info(self, room):
        """
        Shows info about a tinychat room.
        :param room: str tinychat room.
        """
        if self.is_client_mod:
            if len(room) is 0:
                self.send_undercover_msg(self.active_user.nick, 'Missing room to search for.')
            else:
                tc_usr = pinylib.apis.tinychat.room_info(room)
                if tc_usr is None:
                    self.send_undercover_msg(self.active_user.nick, 'Could not find tinychat info for: ' + room)
                else:
                    self.send_bot_msg('*Room ID:* ' + tc_usr['tinychat_id'])

    # == Other API Command Methods. ==
    def do_search_urban_dictionary(self, search_str):
        """ Shows urbandictionary definition of search string.

        :param search_str: The search string to look up a definition for.
        :type search_str: str
        """
        if self.is_client_mod:
            if len(search_str) is 0:
                self.send_bot_msg('Please specify something to look up.')
            else:
                urban = other.urbandictionary_search(search_str)
                if urban is None:
                    self.send_bot_msg('Could not find a definition for: ' + search_str)
                else:
                    if len(urban) > 85:
                        chunks = pinylib.string_util.chunk_string(urban, 85)
                        for i in range(0, 3):
                            self.send_bot_msg(chunks[i])
                    else:
                        self.send_bot_msg(urban)

    def do_whois_ip(self, ip_str):
        """ Shows whois info for a given ip address or domain.

        :param ip_str: The ip address or domain to find info for.
        :type ip_str: str
        """
        if len(ip_str) is 0:
            self.send_bot_msg('Please provide an IP address.')
        else:
            whois = other.whois(ip_str)
            if whois is None:
                self.send_bot_msg('No info found for: %s' % ip_str)
            else:
                self.send_bot_msg(whois)

    def do_advice(self):
        """ Shows a random response from api.adviceslip.com """
        advised = other.advice()
        if advised is not None:
            self.send_bot_msg(advised)

    def do_time(self, location):
        """ Shows the time in a location using Time.is. """
        times = str(other.time_is(location))
        if len(location) is 0:
            self.send_bot_msg(' Please enter a location to fetch the time.')
        else:
            if times is None:
                self.send_bot_msg(' We could not fetch the time in "' + str(location) + '".')
            else:
                self.send_bot_msg('The time in *' + str(location) + '* is: *' + str(times) + "*")

    def do_translate(self, cmd_arg):
        if len(cmd_arg) is 0:
            self.send_bot_msg("Please enter a query to be translated to English, Example: translate jeg er fantastisk")
        else:
            translated_reply = other.translate(query=cmd_arg)
            self.send_bot_msg("In English: " + "*" + translated_reply + "*")

    # == Just For Fun Command Methods. ==
    def do_chuck_norris(self):
        """ Shows a chuck norris joke/quote. """
        chuck = other.chuck_norris()
        if chuck is not None:
            self.send_bot_msg(chuck)

    def do_8ball(self, question):
        """ Shows magic eight ball answer to a yes/no question.

        :param question: The yes/no question.
        :type question: str
        """
        if len(question) is 0:
            self.send_bot_msg('Question.')
        else:
            self.send_bot_msg('*8Ball* %s' % locals_.eight_ball())

    def do_dice(self):
        """ roll the dice. """
        self.send_bot_msg('*The dice rolled:* %s' % locals_.roll_dice())

    def do_flip_coin(self):
        """ Flip a coin. """
        self.send_bot_msg('*The coin was:* %s' % locals_.flip_coin())

    # Private Message Command Handler.
    def private_message_handler(self, private_msg):
        """ A user private message the client.

        :param private_msg: The private message.
        :type private_msg: str
        """
        if private_msg:
            pm_parts = private_msg.split(' ')
            pm_cmd = pm_parts[0].lower().strip()
            pm_arg = ' '.join(pm_parts[1:]).strip()

            # Super admin commands.
            if self.has_level(1):
                if self.is_client_owner:
                    # Only possible if bot is using the room owner account.
                    if pm_cmd == 'mod':
                        threading.Thread(target=self.do_make_mod, args=(pm_arg,)).start()

                    elif pm_cmd == 'removemod':
                        threading.Thread(target=self.do_remove_mod, args=(pm_arg,)).start()

                    elif pm_cmd == 'directory':
                        threading.Thread(target=self.do_directory).start()

                    elif pm_cmd == 'p2t':
                        threading.Thread(target=self.do_push2talk).start()

                    elif pm_cmd == 'green':
                        threading.Thread(target=self.do_green_room).start()

                    elif pm_cmd == 'clearbans':
                        threading.Thread(target=self.do_clear_room_bans).start()

                    elif pm_cmd == 'kill':
                        self.do_kill()

                    elif pm_cmd == 'reboot':
                        self.do_reboot()

                    elif pm_cmd == 'key':
                        self.do_key(pm_arg)

                    elif pm_cmd == 'clearnicks':
                        self.do_clear_bad_nicks()

                    elif pm_cmd == 'clearwords':
                        self.do_clear_bad_strings()

                    elif pm_cmd == 'clearaccounts':
                        self.do_clear_bad_accounts()

            # Admin commands - Bot Controller using key.
            if self.has_level(2):
                if pm_cmd == 'public':
                    self.do_public_cmds()

                elif pm_cmd == 'roompassword':
                    threading.Thread(target=self.do_set_room_pass, args=(pm_arg,)).start()

                elif pm_cmd == 'campassword':
                    threading.Thread(target=self.do_set_broadcast_pass, args=(pm_arg,)).start()
            # Mod commands.
            if self.has_level(3):
                # Misc
                if pm_cmd == 'op':
                    self.do_op_user(pm_arg)

                elif pm_cmd == 'deop':
                    self.do_deop_user(pm_arg)

                elif pm_cmd == 'greeting':
                    self.do_greet()

                elif pm_cmd == 'settings':
                    self.do_room_settings()

                elif pm_cmd == 'clear':
                    self.do_clear()

                elif pm_cmd == 'nick':
                    self.do_nick(pm_arg)

                elif pm_cmd == 'topic':
                    self.do_topic(pm_arg)

                elif pm_cmd == 'list':
                    self.do_list_info(pm_arg)

                elif pm_cmd == 'uinfo':
                    self.do_user_info(pm_arg)

                # Video/Audio
                elif pm_cmd == 'up':
                    self.do_cam_up()

                elif pm_cmd == 'down':
                    self.do_cam_down()

                elif pm_cmd == 'nocam':
                    self.do_nocam()

                elif pm_cmd == 'close':
                    self.do_close_broadcast(pm_arg)

                elif pm_cmd == 'cam':
                    threading.Thread(target=self.do_cam_approve).start()

                # Anti-spam
                elif pm_cmd == 'kick':
                    threading.Thread(target=self.do_kick, args=(pm_arg,)).start()

                elif pm_cmd == 'ban':
                    threading.Thread(target=self.do_ban, args=(pm_arg,)).start()

                elif pm_cmd == 'badnick':
                    self.do_bad_nick(pm_arg)

                elif pm_cmd == 'removenick':
                    self.do_remove_bad_nick(pm_arg)

                elif pm_cmd == 'badstring':
                    self.do_bad_string(pm_arg)

                elif pm_cmd == 'removeword':
                    self.do_remove_bad_string(pm_arg)

                elif pm_cmd == 'badaccount':
                    self.do_bad_account(pm_arg)

                elif pm_cmd == 'goodaccount':
                    self.do_remove_bad_account(pm_arg)

                elif pm_cmd == 'noguest':
                    self.do_guests()

                elif pm_cmd == 'lurkers':
                    self.do_lurkers()

                elif pm_cmd == 'guestnick':
                    self.do_guest_nicks()

                elif pm_cmd == 'newusers':
                    self.do_newusers()

            if self.has_level(4):
                if pm_cmd == 'pm':
                    self.do_pm_bridge(pm_parts)

            # Public commands.
            if self.has_level(5):
                if pm_cmd == 'opme':
                    self.do_opme(pm_arg)

                elif pm_cmd == 'pm':
                    self.do_pm_bridge(pm_parts)

        # Print to console.
        msg = str(private_msg).replace(pinylib.CONFIG.B_KEY, '***KEY***'). \
            replace(pinylib.CONFIG.B_SUPER_KEY, '***SUPER KEY***')
        self.console_write(pinylib.COLOR['white'], 'Private message from %s: %s' % (self.active_user.nick, msg))

    def do_set_room_pass(self, password):
        """ Set a room password for the room.

        :param password: The room password.
        :type password: str | None
        """
        if self.is_client_owner:
            if not password:
                self.privacy_settings.set_room_password()
                self.send_bot_msg('*The room password was removed.*')
                pinylib.time.sleep(1)
                self.send_private_msg('The room password was removed.', self.active_user.nick)
            elif len(password) > 1:
                self.privacy_settings.set_room_password(password)
                self.send_private_msg('*The room password is now:* ' + password, self.active_user.nick)
                pinylib.time.sleep(1)
                self.send_bot_msg('*The room is now password protected.*')

    def do_set_broadcast_pass(self, password):
        """ Set a broadcast password for the room.

        :param password: The broadcast password.
        :type password: str | None
        """
        if self.is_client_owner:
            if not password:
                self.privacy_settings.set_broadcast_password()
                self.send_private_msg('*The broadcast password was removed.*', self.active_user.nick)
                pinylib.time.sleep(1)
                self.send_private_msg('The broadcast password was removed.', self.active_user.nick)
            elif len(password) > 1:
                self.privacy_settings.set_broadcast_password(password)
                self.send_private_msg('*The broadcast password is now:* ' + password, self.active_user.nick)
                pinylib.time.sleep(1)
                self.send_private_msg('*Broadcast password is enabled.*', self.active_user.nick)

    def do_key(self, new_key):
        """ Shows or sets a new secret key.

        :param new_key: The new secret key.
        :type new_key: str
        """
        if len(new_key) is 0:
            self.send_private_msg('The current key is: *%s*' % pinylib.CONFIG.B_KEY, self.active_user.nick)
        elif len(new_key) < 6:
            self.send_private_msg('*Key must be at least 6 characters long:* %s' % len(new_key),
                                  self.active_user.nick)
        elif len(new_key) >= 6:
            # reset all bot controllers back to normal users
            for user in self.users.all:
                if self.users.all[user].user_level is 2 or self.users.all[user].user_level is 4:
                    self.users.all[user].user_level = 5
            pinylib.CONFIG.B_KEY = new_key
            self.send_private_msg('The key was changed to: *%s*' % new_key, self.active_user.nick)

    def do_clear_bad_nicks(self):
        """ Clears the bad nicks file. """
        pinylib.CONFIG.B_NICK_BANS[:] = []
        pinylib.file_handler.delete_file_content(self.config_path(), pinylib.CONFIG.B_NICK_BANS_FILE_NAME)

    def do_clear_bad_strings(self):
        """ Clears the bad strings file. """
        pinylib.CONFIG.B_STRING_BANS[:] = []
        pinylib.file_handler.delete_file_content(self.config_path(), pinylib.CONFIG.B_STRING_BANS_FILE_NAME)

    def do_clear_bad_accounts(self):
        """ Clears the bad accounts file. """
        pinylib.CONFIG.B_ACCOUNT_BANS[:] = []
        pinylib.file_handler.delete_file_content(self.config_path(), pinylib.CONFIG.B_ACCOUNT_BANS_FILE_NAME)

    # == Public PM Command Methods. ==
    def do_opme(self, key):
        """ Makes a user a bot controller if user provides the right key.

        :param key: A secret key.
        :type key: str
        """
        if len(key) is 0:
            self.send_private_msg('Missing key.', self.active_user.nick)
        elif key == pinylib.CONFIG.B_SUPER_KEY:
            if self.is_client_owner:
                self.active_user.user_level = 1
                self.send_private_msg('*You are now super admin.*', self.active_user.nick)
            else:
                self.send_private_msg('*The client is not using the owner account.*', self.active_user.nick)
        elif key == pinylib.CONFIG.B_KEY:
            if self.is_client_mod:
                self.active_user.user_level = 2
                self.send_private_msg('*You are now administrator (Level 2).*', self.active_user.nick)
                self.send_private_msg('Commands https://github.com/Tinychat/Tinychat-Bot/wiki#Level-2',
                                      self.active_user.nick)
            else:
                self.send_private_msg('*The client is not moderator.*', self.active_user.nick)
        else:
            self.send_private_msg('Wrong key.', self.active_user.nick)

    def do_pm_bridge(self, pm_parts):
        """ Makes the bot work as a PM message bridge between 2 user who are not signed in.

        :param pm_parts: The pm message as a list.
        :type pm_parts: list
        """
        if len(pm_parts) == 1:
            self.send_private_msg('Missing username.', self.active_user.nick)
        elif len(pm_parts) == 2:
            self.send_private_msg('The command is: ' + pinylib.CONFIG.B_PREFIX + 'pm username message',
                                  self.active_user.nick)
        elif len(pm_parts) >= 3:
            pm_to = pm_parts[1]
            msg = ' '.join(pm_parts[2:])
            is_user = self.users.search(pm_to)
            if is_user is not None:
                if is_user.id == self._client_id:
                    self.send_private_msg('Action not allowed.', self.active_user.nick)
                else:
                    self.send_private_msg('*<' + self.active_user.nick + '>* ' + msg, pm_to)
            else:
                self.send_private_msg('No user named: ' + pm_to, self.active_user.nick)

    # Helper Methods.
    def get_privacy_settings(self):
        """ Parse the privacy settings page. """
        log.info('Parsing %s\'s privacy page. Proxy %s' % (self.account, self._proxy))
        self.privacy_settings = privacy.Privacy(self._proxy)
        self.privacy_settings.parse_privacy_settings()

    def config_path(self):
        """ Returns the path to the rooms configuration directory. """
        path = pinylib.CONFIG.CONFIG_PATH + self.roomname + '/'
        return path

    def load_list(self, nicks=False, accounts=False, strings=False):
        """
        Loads different list to memory.
        :param nicks: bool, True load nick bans file.
        :param accounts: bool, True load account bans file.
        :param strings: bool, True load ban strings file.
        """
        if nicks:
            pinylib.CONFIG.B_NICK_BANS = pinylib.file_handler.file_reader(self.config_path(),
                                                                          pinylib.CONFIG.B_NICK_BANS_FILE_NAME)
        if accounts:
            pinylib.CONFIG.B_ACCOUNT_BANS = pinylib.file_handler.file_reader(self.config_path(),
                                                                             pinylib.CONFIG.B_ACCOUNT_BANS_FILE_NAME)
        if strings:
            pinylib.CONFIG.B_STRING_BANS = pinylib.file_handler.file_reader(self.config_path(),
                                                                            pinylib.CONFIG.B_STRING_BANS_FILE_NAME)

    def has_level(self, level):
        """ Checks the active user for correct user level.

        :param level: The level to check the active user against.
        :type level: int
        """
        if self.active_user.user_level is 6:
            return False
        elif self.active_user.user_level <= level:
            return True
        return False

    @staticmethod
    def format_time(milliseconds):
        """ Converts milliseconds to (day(s)) hours minutes seconds.

        :param milliseconds: Milliseconds to convert.
        :return: A string in the format (days) hh:mm:ss
        :rtype: str
        """
        m, s = divmod(milliseconds / 1000, 60)
        h, m = divmod(m, 60)
        d, h = divmod(h, 24)

        if d == 0 and h == 0:
            human_time = '%02d:%02d' % (m, s)
        elif d == 0:
            human_time = '%d:%02d:%02d' % (h, m, s)
        else:
            human_time = '%d Day(s) %d:%02d:%02d' % (d, h, m, s)
        return human_time

    def check_msg(self, msg):
        """ Checks the chat message for bad string.

        :param msg: The chat message.
        :type msg: str
        """
        was_banned = False
        chat_words = msg.split(' ')
        for bad in pinylib.CONFIG.B_STRING_BANS:
            if bad.startswith('*'):
                _ = bad.replace('*', '')
                if _ in msg:
                    self.send_ban_msg(self.active_user.nick, self.active_user.id)
                    was_banned = True
            elif bad in chat_words:
                self.send_ban_msg(self.active_user.nick, self.active_user.id)
                was_banned = True
        if was_banned and pinylib.CONFIG.B_FORGIVE_AUTO_BANS:
            self.send_forgive_msg(self.active_user.id)

    def check_nick(self, old, user_info):
        """ Check a users nick.

        :param old: The old nick name of the user.
        :type old: str
        :param user_info: The User object. This will contain the new nick.
        :type user_info: User
        """
        if self._client_id != user_info.id:
            if str(old).startswith('guest-') and self.is_client_mod:
                if str(user_info.nick).startswith('guest-'):
                    if not pinylib.CONFIG.B_ALLOW_GUESTS_NICKS:
                        self.send_ban_msg(user_info.nick, user_info.id)
                        self.send_bot_msg('*Auto-Banned:* (bot nick detected)')
                        return True
                if str(user_info.nick).startswith('newuser'):
                    if not pinylib.CONFIG.B_ALLOW_NEWUSERS:
                        self.send_ban_msg(user_info.nick, user_info.id)
                        self.send_bot_msg('*Auto-Banned:* (wanker detected)')
                        return True
                if len(pinylib.CONFIG.B_NICK_BANS) > 0:
                    for bad_nick in pinylib.CONFIG.B_NICK_BANS:
                        if bad_nick.startswith('*'):
                            a = bad_nick.replace('*', '')
                            if a in user_info.nick:
                                self.send_ban_msg(user_info.nick, user_info.id)
                                self.send_bot_msg('*Auto-Banned:* (*bad nick)')
                                return True
                        elif user_info.nick in pinylib.CONFIG.B_NICK_BANS:
                            self.send_ban_msg(user_info.nick, user_info.id)
                            self.send_bot_msg('*Auto-Banned:* (bad nick)')
                            return True
                return False
