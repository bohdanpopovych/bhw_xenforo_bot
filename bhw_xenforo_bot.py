import email
import imaplib
import smtplib

import re
from selenium import webdriver
from datetime import datetime
from time import sleep
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait


class ForumMessage:
    def __init__(self, number, url, author, content):
        self.PostNumber = int(number)
        self.Url = str(url)
        self.Author = str(author)
        self.Content = str(content)


def send_email(user, pwd, recipient, subject, body):
    gmail_user = user
    gmail_pwd = pwd
    FROM = user
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


def process_mailbox(m, email_from):
    results = {}
    rv, data = m.search(None, "(UNSEEN FROM {} SINCE {})".format(email_from, datetime.now().strftime('%d-%b-%Y')))
    if rv != 'OK':
        print('No messages found!')
        return

    for num in data[0].split():
        rv, data = m.fetch(num, '(RFC822)')
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


def get_emails(username, password):
    email_folder = 'INBOX'
    results = {}
    m = imaplib.IMAP4_SSL('imap.gmail.com')

    try:
        rv, data = m.login(username + '@gmail.com', password)
    except imaplib.IMAP4.error:
        print('LOGIN FAILED!!! ')

    rv, mailboxes = m.list()
    rv, data = m.select(email_folder)

    if rv == 'OK':
        results = process_mailbox(m, email_confirm)
        m.close()
    else:
        print('ERROR: Unable to open mailbox ', rv)

    m.logout()

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


def get_last_message_number() -> int:
    driver.get(forum_thread)

    messages = driver.find_element_by_id('messageList').find_elements_by_class_name('message')

    # Getting last message number
    _last_message_number = int(
        messages[-1].find_element_by_xpath(".//div/a[contains(@class, 'item')]").text[1:]
    )

    return _last_message_number


# Check if messages contains keywords
def check_messages(messages):
    results = []
    for message in messages:
        for keyword in keywords:
            if message.Content.find(keyword) != -1:
                results.append(message)
                break

    return results


def get_new_messages():
    results_list = []
    driver.get(forum_thread)
    messages = driver.find_element_by_id('messageList').find_elements_by_class_name('message')

    bhw_nickname = driver.find_element_by_class_name('accountUsername').text

    for message in messages:
        message_author = message.get_attribute('data-author')

        # Do not send messages about yourself
        if message_author == bhw_nickname:
            continue

        message_number_item = message.find_element_by_xpath(".//div/a[contains(@class, 'item')]")
        message_number = int(message_number_item.text[1:])
        message_url = message_number_item.get_attribute('href')

        if message_number <= last_message_number:
            continue

        message_text = message.find_element_by_xpath('.//article/blockquote').text

        new_message = ForumMessage(message_number, message_url, message_author, message_text)
        results_list.append(new_message)

    return results_list


def send_emails(messages):
    for message in messages:
        email_text = 'Author: {}\nMessage: {}'.format(message.Author, message.Content)
        send_email(email_login, email_password, email_confirm, message.Url, email_text)


def send_private_message(url, message_text, title='title'):
    driver.get(url)
    post_number = url.split('#')[-1]

    post_author = driver.find_element_by_xpath(
        '//a[contains(@href, "{}")]/../../..'.format(post_number)).get_attribute('data-author')

    start_conversation_url = 'https://www.blackhatworld.com/conversations/add?to=' + post_author

    driver.get(start_conversation_url)

    WebDriverWait(driver, 10).until(EC.presence_of_element_located, (By.XPATH, '//*[@name="title"]'))

    title_element = driver.find_element_by_xpath('//*[@name="title"]')

    title_element.send_keys(title)
    sleep(1)

    # Switching to <iframe> with editor body
    driver.switch_to.frame(driver.find_element_by_xpath('//div/iframe'))
    editor_body = driver.find_element_by_xpath('//body/p')
    editor_body.send_keys(message_text)


    print('Private message to {} has been sent'.format(post_author))
    pass


def send_private_messages(response):
    for key, item in response.items():
        filtered_messages = list(filter(lambda x: x.Url == key, pending_messages))
        if filtered_messages:
            message = filtered_messages[0]
            send_private_message(message.Url, private_message_text)


forum_thread = \
    'https://www.blackhatworld.com/seo/zero-to-profit-make-bank-with-shopify-stores-with-facebook-ads.969878/' + \
    'page-99999'

keywords = ['discount', 'Samples', 'samples']

email_login, email_password = 'bohdan.popovych.08', 'bqmyinivoaectxdn'
email_confirm = 'bodyanu4@gmail.com'
private_message_text = 'Sample text'

# Milliseconds
refresh_period = 1000

# Setting up firefox to block loading images to speed up bot
firefox_profile = webdriver.FirefoxProfile()
firefox_profile.set_preference('permissions.default.image', 2)
firefox_profile.set_preference('dom.ipc.plugins.enabled.libflashplayer.so', 'false')

driver = webdriver.Firefox(firefox_profile=firefox_profile)

login('bohdan.popovych.08@gmail.com', 'therat4ever')

# TODO: remove after testing
last_message_number = 41  # get_last_message_number()

pending_messages = []

while True:
    try:
        new_messages = check_messages(get_new_messages())

        send_emails(new_messages)
        pending_messages.extend(new_messages)

        # noinspection PyRedeclaration
        last_message_number = get_last_message_number()

        sleep(refresh_period / 1000)

        responses = get_emails(email_login, email_password)
        send_private_messages(responses)

    except WebDriverException:
        print('Cannot connect to BHW...\nRetrying in 10s...')
        sleep(10)