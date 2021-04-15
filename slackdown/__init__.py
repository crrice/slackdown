import re
import copy
try:
    # Python 2 module
    from HTMLParser import HTMLParser
except ImportError:
    # Python 3 module
    from html.parser import HTMLParser

DEBUG = False

"""
Slack characters that serve as delimination options.
"""
LIST_DELIMITERS = {
    '\-': 'dash',
    "[{}]".format(''.join([u'\u2022', u'\u25e6', u'\u25aa', '\*'])): 'dot',
    '\w*\.': 'numbered',
}

"""
Slack characters that serve as formatting options.
"""
FORMATTERS = {
    '*': 'b',
    '_': 'i',
    '~': 's',
    '`': 'code',
}

"""
List types outputed by slackdown.render().
"""
LIST_TYPES = {
    'dot': 'ul',
    'dash': 'ul',
    'numbered': 'ol',
}

"""
Predefined elements that serve as "parents".
"""
PARENT_ELEMENTS = [
    'p',
    'pre',
    'ul',
    'ol',
    'blockquote'
]


def parse(message):
    """
    Accepts a Slack message object and returns HTML.
    """
    html = render(message['text'])

    return html


def render(txt):
    """
    Accepts Slack formatted text and returns HTML.
    """
    if DEBUG:
        print("Initial text: %s" % list(txt))

    # Removing links to other channels
    txt = re.sub(r'<#[^\|]*\|(.*)>', r'#\g<1>', txt)

    # Removing links to other users
    txt = re.sub(r'<(@.*)>', r'\g<1>', txt)

    # handle named hyperlinks
    txt = re.sub(r'<([^\|]*)\|([^\|]*)>', r'<a href="\g<1>" target="blank">\g<2></a>', txt)

    # handle unnamed hyperlinks
    txt = re.sub(r'<([^a|/a].*)>', r'<a href="\g<1>" target="blank">\g<1></a>', txt)

    # handle ordered and unordered lists
    for delimeter in LIST_DELIMITERS:
        slack_tag = delimeter
        class_name = LIST_DELIMITERS[delimeter]

        # Wrap any lines that start with the slack_tag in <li></li>
        list_regex = r'(?m)^( *){} (.*)\n?'.format(slack_tag)
        list_repl = lambda matchobj: r'<li class="list-item-{} indent-{}">{}</li>'.format(class_name, len(matchobj.group(1)) // 4, matchobj.group(2))
        txt = re.sub(list_regex, list_repl, txt)

        if DEBUG:
            print("Txt after %s:\n%s\n" % (delimeter, txt))

    # hanlde blockquotes
    txt = re.sub(u'(^|\n)(?:&gt;){3}\s?(.*)$', r'\g<1><blockquote>\g<2></blockquote>', txt, flags=re.DOTALL)
    txt = re.sub(u'(?:^|\n)&gt;\s?(.*)\n?', r'<blockquote>\g<1></blockquote>', txt)

    # handle code blocks
    txt = re.sub(r'```\n?(.*)```', r'<pre>\g<1></pre>', txt, flags=re.DOTALL)
    txt = re.sub(r'\n(</pre>)', r'\g<1>', txt)

    # handle bolding, italics, and strikethrough
    for wrapper in FORMATTERS:
        slack_tag = wrapper
        html_tag = FORMATTERS[wrapper]

        # Grab all text in formatted characters on the same line unless escaped
        regex = r'(?<!\\)\{t}([^\{t}|\n]*)\{t}'.format(t=slack_tag)
        repl = r'<{t}>\g<1></{t}>'.format(t=html_tag)
        txt = re.sub(regex, repl, txt)

    # convert line breaks
    txt = txt.replace('\n', '<br />')

    # clean up bad HTML
    parser = CustomSlackdownHTMLParser(txt)
    txt = parser.clean()

    # convert multiple spaces
    txt = txt.replace(r'  ', ' &nbsp;')

    return txt


class CustomSlackdownHTMLParser(HTMLParser):
    """
    Custom HTML parser for cleaning up the slackdown HTML output.
    """
    def __init__(self, txt):
        """
        Initialize custom parser properties.
        """

        if DEBUG:
            print("Dirty HTML: %s\n" % txt)
        self.dirty_html = txt
        self.cleaned_html = ''
        self.current_parent_element = {}
        self.current_parent_element['tag'] = ''
        self.current_parent_element['attrs'] = {}
        self.parsing_li = False # this is not used??
        self.indent_level = 0
        self.list_stack = []

        HTMLParser.__init__(self)

    def _open_list(self, list_type):
        """
        Add an open list tag corresponding to the specification in the
        parser's LIST_TYPES.
        """
        if list_type in LIST_TYPES.keys():
            tag = LIST_TYPES[list_type]
        else:
            raise Exception('CustomSlackdownHTMLParser:_open_list: Not a valid list type.')

        html = '<{t} class="list-container-{c}">'.format(
            t=tag,
            c=list_type
        )
        self.cleaned_html += html
        if self.current_parent_element['tag'] in ['ul', 'ol']:
            self.list_stack.append(copy.deepcopy(self.current_parent_element))
            if DEBUG:
                print("Pushing ", self.current_parent_element['tag'])
            self.indent_level += 1
        self.current_parent_element['tag'] = LIST_TYPES[list_type]
        self.current_parent_element['attrs'] = {'class': list_type}


    def _close_list(self):
        """
        Add an close list tag corresponding to the currently open
        list found in current_parent_element.
        """
        list_type = self.current_parent_element['attrs']['class']
        tag = LIST_TYPES[list_type]

        html = '</{t}>'.format(
            t=tag
        )
        self.cleaned_html += html
        if not self.list_stack:
            self.current_parent_element['tag'] = ''
            self.current_parent_element['attrs'] = {}

        else:
            self.current_parent_element = self.list_stack.pop()
            if DEBUG:
                print("Popping ", self.current_parent_element['tag'])
            self.indent_level -= 1



    def handle_starttag(self, tag, attrs):
        """
        Called by HTMLParser.feed when a start tag is found.
        """
        if DEBUG:
            print("Handle starttag %s\nCurrent Parent: %s\nParent List: %s" % (tag, self.current_parent_element, self.list_stack))
        # Parse the tag attributes
        attrs_dict = dict(t for t in attrs)

        # If the tag is a predefined parent element
        if tag in PARENT_ELEMENTS:
            # If parser is parsing another parent element
            if self.current_parent_element['tag'] != '':
                # close the parent element
                self.cleaned_html += '</{}>'.format(self.current_parent_element['tag'])
                if self.current_parent_element['tag'] in ['ol', 'ul']:
                    while self.indent_level > 0:
                        self._close_list()
                    self._close_list()

            self.current_parent_element['tag'] = tag
            self.current_parent_element['attrs'] = {}

            self.cleaned_html += '<{}>'.format(tag)

        # If the tag is a list item
        elif tag == 'li':
            self.parsing_li = True

            # Parse the class name & subsequent type
            class_arr = attrs_dict['class'].split(' ')
            class_name = class_arr[0]
            list_type = class_name[10:]
            indent_level = int(class_arr[1][7:])

            # Check if parsing a list
            if (self.current_parent_element['tag'] == 'ul' or self.current_parent_element['tag'] == 'ol') and (indent_level == self.indent_level):
                cur_list_type = self.current_parent_element['attrs']['class']
                # Parsing a different list
                if cur_list_type != list_type:
                    # Close that list
                    #self._close_list()

                    # Open new list
                    self._open_list(list_type)

            # Parent tag is list, indent levels do not match
            elif (self.current_parent_element['tag'] == 'ul' or self.current_parent_element['tag'] == 'ol'):

                if indent_level < self.indent_level:
                    while indent_level < self.indent_level:
                        self._close_list()
                else:
                    while indent_level > self.indent_level:
                        self._open_list(list_type)

            # Not parsing a list
            else:
                # if parsing some other parent
                if self.current_parent_element['tag'] != '':
                    self.cleaned_html += '</{}>'.format(self.current_parent_element['tag'])
                # Open new list
                self._open_list(list_type)

            self.cleaned_html += '<{}>'.format(tag)

        # If the tag is a line break
        elif tag == 'br':
            # If parsing a paragraph, close it
            if self.current_parent_element['tag'] == 'p':
                self.cleaned_html += '</p>'
                if not self.list_stack:
                    self.current_parent_element['tag'] = ''
                    self.current_parent_element['attrs'] = {}
                else:
                    self.current_parent_element = self.list_stack.pop()
            # If parsing a list, close it
            elif self.current_parent_element['tag'] == 'ul' or self.current_parent_element['tag'] == 'ol':
                while self.indent_level > 0:
                    self._close_list()
                self._close_list()
            # If parsing any other parent element, keep it
            elif self.current_parent_element['tag'] in PARENT_ELEMENTS:
                self.cleaned_html += '<br />'
            # If not in any parent element, create an empty paragraph
            else:
                self.cleaned_html += '<p></p>'

        # If the tag is something else, like a <b> or <i> tag
        else:
            # If not parsing any parent element
            if self.current_parent_element['tag'] == '':
                self.cleaned_html += '<p>'
                self.current_parent_element['tag'] = 'p'
            self.cleaned_html += '<{}'.format(tag)

            for attr in sorted(attrs_dict.keys()):
                self.cleaned_html += ' {k}="{v}"'.format(
                    k=attr,
                    v=attrs_dict[attr]
                )

            self.cleaned_html += '>'


    def handle_endtag(self, tag):
        """
        Called by HTMLParser.feed when an end tag is found.
        """
        if DEBUG:
            print("Handle endtag %s\nCurrent Parent: %s\nParent List: %s" % (tag, self.current_parent_element, self.list_stack))
        if tag in PARENT_ELEMENTS:
            if self.list_stack:
                self.current_parent_element = self.list_stack.pop()
            else:
                self.current_parent_element['tag'] = ''
                self.current_parent_element['attrs'] = ''

        if tag == 'li':
            self.parsing_li = True
        if tag != 'br':
            self.cleaned_html += '</{}>'.format(tag)


    def handle_data(self, data):
        """
        Called by HTMLParser.feed when text is found.
        """
        if DEBUG:
            print("Handle data %s\nCurrent Parent: %s\nParent List: %s" % (data, self.current_parent_element, self.list_stack))
        if self.current_parent_element['tag'] == '':
            self.cleaned_html += '<p>'
            self.current_parent_element['tag'] = 'p'

        self.cleaned_html += data


    def _remove_pre_formatting(self):
        """
        Removes formatting tags added to pre elements.
        """
        preformatted_wrappers = [
            'pre',
            'code'
        ]

        for wrapper in preformatted_wrappers:
            for formatter in FORMATTERS:
                tag = FORMATTERS[formatter]
                character = formatter

                regex = r'(<{w}>.*)<{t}>(.*)</{t}>(.*</{w}>)'.format(
                    t=tag,
                    w=wrapper
                )
                repl = r'\g<1>{c}\g<2>{c}\g<3>'.format(c=character)
                self.cleaned_html = re.sub(regex, repl, self.cleaned_html)

    def feed(self):
        """
        Uses the dirty_html property as the argument for HTMLParser.feed
        """
        HTMLParser.feed(self, self.dirty_html)

    def clean(self):
        """
        Goes through the txt input and cleans up any problematic HTML.
        """
        # Calls handle_starttag, handle_endtag, and handle_data
        self.feed()

        # Clean up any parent tags left open
        if self.current_parent_element['tag'] != '':
            self.cleaned_html += '</{}>'.format(self.current_parent_element['tag'])

        # Remove empty <p> added after lists
        self.cleaned_html = re.sub(r'(</[u|o]l>)<p></p>', r'\g<1>', self.cleaned_html)

        self._remove_pre_formatting()

        return self.cleaned_html
