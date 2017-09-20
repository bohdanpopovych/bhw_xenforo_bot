import email
import imaplib
import smtplib
import re
import configparser
import codecs

from multiprocessing.pool import Pool

from selenium import webdriver
from datetime import datetime
from time import sleep
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait


class ThreadSettingsModule:
    def __init__(self,
                 thread_url,
                 keywords,
                 email_wrapper,
                 message_title,
                 message_body):
        self.keywords = keywords
        self.thread_url = thread_url
        self.email_wrapper = email_wrapper
        self.message_title = message_title
        self.message_body = message_body


class GlobalSettings:
    def __init__(self, file_name):
        self.file_name = file_name
        self.forum_username = str()
        self.forum_password = str()
        self.refresh_period = int()
        self.email_username = str()
        self.email_password = str()
        self.control_email = str()
        self.email_wrapper = None

    def get_settings_from_file(self):
        config = configparser.ConfigParser()
        config.read(self.file_name)

        threads_settings_list = []

        try:
            for section in config.sections():
                if section == 'GLOBAL':
                    self.forum_username = config[section]['forum_login']
                    self.forum_password = config[section]['forum_password']
                    self.refresh_period = int(config[section]['refresh_period'])
                    self.email_username = config[section]['email_username']
                    self.email_password = config[section]['email_password']
                    self.control_email = config[section]['control_email']
                else:
                    if self.email_wrapper is None:
                        self.email_wrapper = EmailWrapper(
                            self.email_username,
                            self.email_password,
                            self.control_email)

                    new_thread = ThreadSettingsModule(
                        thread_url=config[section]['thread_url'],
                        keywords=config[section]['keywords'].split(','),
                        message_title=config[section]['message_title'],
                        message_body=codecs.decode(
                            config[section]['message_body'], 'unicode_escape', 'ignore'),
                        email_wrapper=self.email_wrapper
                    )

                    threads_settings_list.append(new_thread)

            return threads_settings_list

        except KeyError as ex:
            print('settings.ini file is invalid!\nCheck all values and try again!')
            quit()


class ForumMessage:
    def __init__(self, number, url, author, content):
        self.post_number = int(number)
        self.url = str(url)
        self.author = str(author)
        self.content = str(content)


class ForumThread:
    def __init__(self):
        self.driver = None
        self.url = ''
        self.pending_messages = []
        self.last_message_number = 0
        self.keywords = []
        self.email_wrapper = None

    def init_from_settings(self, settings: ThreadSettingsModule, _driver):
            self.driver = _driver
            self.url = settings.thread_url
            self.pending_messages = []
            self.keywords = settings.keywords
            self.email_wrapper = None

            self.email_wrapper = settings.email_wrapper

    def setup_email(self, _username, _password, _control_email):
        self.email_wrapper = EmailWrapper(_username, _password, _control_email)

    def scan_thread(self):
        try:
            self.last_message_number = self.get_last_message_number()

            new_messages = self.check_messages(self.get_new_messages())

            self.send_emails(new_messages)
            self.pending_messages.extend(new_messages)

            # noinspection PyRedeclaration
            self.last_message_number = self.get_last_message_number()

            responses = self.email_wrapper.get_emails()
            self.send_private_messages(responses)

        except WebDriverException as ex:
            print('Cannot connect to BHW...\nSkipping this attempt...')

    def send_private_message(self, url, message_text, title='title'):
        self.driver.get(self.url)
        post_number = url.split('#')[-1]

        post_author = self.driver.find_element_by_xpath(
            '//a[contains(@href, "{}")]/../../..'.format(post_number)).get_attribute('data-author')

        start_conversation_url = 'https://www.blackhatworld.com/conversations/add?to=' + post_author

        self.driver.get(start_conversation_url)

        WebDriverWait(self.driver, 10) \
            .until(EC.presence_of_element_located, (By.XPATH, '//*[@name="title"]'))

        title_element = self.driver.find_element_by_xpath('//*[@name="title"]')

        title_element.send_keys(title)
        sleep(1)

        # Switching to <iframe> with editor body
        self.driver.switch_to.frame(
            self.driver.find_element_by_xpath('//iframe[contains(@class, "redactor_textCtrl")]'))

        # Waiting for <iframe> content to be loaded
        WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'p')))

        editor_body = self.driver.find_element_by_tag_name('p')
        # In order to switch focus to multiline edit
        editor_body.send_keys(Keys.TAB)
        editor_body.send_keys(message_text)

        self.driver.switch_to.default_content()

        start_button = self.driver.find_element_by_xpath('//input[contains(@value, "Start a Conversation")]')
        start_button.click()

        print('Private message to {} has been sent'.format(post_author))

    def send_private_messages(self, response):
        for key, item in response.items():
            filtered_messages = list(filter(lambda x: x.Url == key, self.pending_messages))
            if filtered_messages:
                message = filtered_messages[0]
                self.send_private_message(message.Url, private_message_text)

    def get_last_message_number(self):
        self.driver.get(self.url)

        WebDriverWait(self.driver, 10).until(EC.presence_of_element_located, (By.ID, 'messageList'))

        messages = self.driver.find_element_by_id('messageList').find_elements_by_class_name('message')

        # Getting last message number. get_attribute('text') is hack due to
        # PhantomJS bug - not returning text properly
        _last_message_number = messages[-1].find_element_by_xpath(".//div/a[contains(@class, 'item')]") \
            .get_attribute('text')

        return int(_last_message_number[1:])

    # Check if messages contains keywords
    def check_messages(self, messages):
        results = []
        for message in messages:
            for keyword in self.keywords:
                if message.content.lower().find(keyword.lower()) != -1:
                    results.append(message)
                    break

        return results

    def get_new_messages(self):
        results_list = []
        self.driver.get(self.url)
        messages = self.driver.find_element_by_id('messageList').find_elements_by_class_name('message')

        bhw_nickname = self.driver.find_element_by_class_name('accountUsername').text

        for message in messages:
            message_author = message.get_attribute('data-author')

            # Do not send messages about yourself
            if message_author == bhw_nickname:
                continue

            message_number_item = message.find_element_by_xpath(".//div/a[contains(@class, 'item')]")
            # Using get_attribute('text') hack again. PhantomJS bug - not returning text properly
            message_number = int(message_number_item.get_attribute('text')[1:])
            message_url = message_number_item.get_attribute('href')

            if message_number <= self.last_message_number:
                continue

            message_text = message.find_element_by_xpath('.//article/blockquote').text

            new_message = ForumMessage(message_number, message_url, message_author, message_text)
            results_list.append(new_message)

        return results_list

    def send_emails(self, messages):
        for message in messages:
            email_text = 'Author: {}\nMessage: {}'.format(message.author, message.content)
            self.email_wrapper.send_email(message.url, email_text)


class EmailWrapper:
    def __init__(self, username, password, control_email):
        self.username = str(username)
        self.password = str(password)
        self.inbox = imaplib.IMAP4_SSL('imap.gmail.com')
        self.control_email = str(control_email)

        self.login()

    def send_email(self, subject, body):
        recipient = self.control_email
        gmail_user = self.username
        gmail_pwd = self.password
        FROM = self.username
        TO = recipient if type(recipient) is list else [recipient]
        SUBJECT = subject
        TEXT = body

        # Prepare actual message
        message = '''From: %s\nTo: %s\nSubject: %s\n\n%s
        ''' % (FROM, ', '.join(TO), SUBJECT, TEXT)
        try:
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.ehlo()
            server.starttls()
            server.login(gmail_user, gmail_pwd)
            server.sendmail(FROM, TO, message)
            server.close()
            print('successfully sent e-mail about #{}'.format(SUBJECT.split('#')[-1]))
        except Exception as ex:
            print('failed to send mail')
            print(ex)

    def process_mailbox(self):
        results = {}
        rv, data = self.inbox.search(None, "(UNSEEN FROM {} SINCE {})".format(self.control_email,
                                                                              datetime.now().strftime('%d-%b-%Y')))
        if rv != 'OK':
            print('No messages found!')
            return

        for num in data[0].split():
            rv, data = self.inbox.fetch(num, '(RFC822)')
            if rv != 'OK':
                print('ERROR getting message', num)
                return

            msg = email.message_from_bytes(data[0][1])

            subject = str(email.header.make_header(email.header.decode_header(msg['Subject'])))

            body = ""

            if msg.is_multipart():
                for part in msg.walk():
                    ctype = part.get_content_type()
                    cdispo = str(part.get('Content-Disposition'))

                    # skip any text/plain (txt) attachments
                    if ctype == 'text/plain' and 'attachment' not in cdispo:
                        body = str(part.get_payload(decode=True))  # decode
                        break
            # not multipart
            else:
                body = str(msg.get_payload(decode=True))

            link = re.search("(?P<url>https?://[^\s]+)", subject).group("url")
            results[link] = body[2].lower() == 'y'

        return results

    def login(self):
        self.inbox = imaplib.IMAP4_SSL('imap.gmail.com')
        try:
            rv, data = self.inbox.login(self.username, self.password)
        except imaplib.IMAP4.error as ex:
            print('Email login failed.\nDetails: ' + str(ex))
            quit()

    def logout(self):
        self.inbox.logout()

    def get_emails(self):
        email_folder = 'INBOX'
        results = {}

        rv, mailboxes = self.inbox.list()
        rv, data = self.inbox.select(email_folder)

        if rv == 'OK':
            results = self.process_mailbox()
            self.inbox.close()
        else:
            print('ERROR: Unable to open mailbox ', rv)

        return results


def login(username, password):
    login_url = 'https://www.blackhatworld.com/login'

    while True:
        try:
            driver.get(login_url)
            break
        except WebDriverException:
            print('Cannot connect to BHW...\nRetrying in 10s...')
            sleep(10)

    driver.find_element_by_name('login').send_keys(username)
    sleep(1)

    driver.find_element_by_name('password').send_keys(password)
    sleep(1)

    driver.find_element_by_xpath("//input[@value='Log in']").click()
    sleep(1)

    try:
        driver.find_element_by_link_text('Log in or Sign up')
        login(username, password)

    except NoSuchElementException:
        pass


global_settings = GlobalSettings('settings.ini')
settings_list = global_settings.get_settings_from_file()

print('Starting browser...')
driver = webdriver.PhantomJS()
print('Browser started!')

print('Signing in...')
login('bohdan.popovych.08@gmail.com', 'therat4ever')
print('Signed in successfully!')


while True:
    for thread_settings in settings_list:
        new_forum_thread = ForumThread()
        new_forum_thread.init_from_settings(thread_settings, driver)
        new_forum_thread.scan_thread()

    sleep(global_settings.refresh_period)
