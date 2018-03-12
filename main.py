import os
import time

import sublime_plugin
import sublime


import rainbow_csv.rainbow_utils as rainbow_utils
import rainbow_csv.sublime_rbql as sublime_rbql
#from .rainbow_utils import *

# FIXME remove these 2 imports
import rainbow_csv.rbql_core
from rainbow_csv.rbql_core import rbql


user_home_dir = os.path.expanduser('~')
table_index_path = os.path.join(user_home_dir, '.rbql_table_index')


# FIXME implement CSVLint


def index_decode_delim(delim):
    if delim == 'TAB':
        return '\t'
    return delim


def index_encode_delim(delim):
    if delim == '\t':
        return 'TAB'
    return delim


def try_read_index(index_path):
    lines = []
    try:
        with open(index_path) as f:
            lines = f.readlines()
    except Exception:
        return []
    result = list()
    for line in lines:
        line = line.rstrip('\r\n')
        if not len(line):
            continue
        record = line.split('\t')
        result.append(record)
    return result


def write_index(records, index_path):
    with open(index_path, 'w') as dst:
        for record in records:
            dst.write('\t'.join(record) + '\n')


def get_index_record(index_path, key):
    records = try_read_index(index_path)
    for record in records:
        if len(record) and record[0] == key:
            return record
    return None


def load_rainbow_params(file_path):
    record = get_index_record(table_index_path, file_path)
    if record is not None and len(record) >= 3:
        delim, policy = record[1:3]
        delim = index_decode_delim(delim)
        return (delim, policy)
    return (None, None)


def update_records(records, record_key, new_record):
    for i in range(len(records)):
        if len(records[i]) and records[i][0] == record_key:
            records[i] = new_record
            return
    records.append(new_record)


def save_rainbow_params(file_path, delim, policy):
    records = try_read_index(table_index_path)
    new_record = [file_path, index_encode_delim(delim), policy, '']
    update_records(records, file_path, new_record)
    if len(records) > 100:
        records.pop(0)
    write_index(records, table_index_path)



def get_line_text(view, lnum):
    point = view.text_point(lnum, 0)
    line = view.substr(view.line(point))
    return line


def get_file_line_count(view):
    return view.rowcol(view.size())[0] + 1


def sample_lines(view):
    num_lines = get_file_line_count(view)
    head_count = 10
    sampled_lines = []
    if num_lines <= head_count * 2:
        for lnum in range(num_lines):
            sampled_lines.append(get_line_text(view, lnum))
    else:
        for lnum in range(head_count):
            sampled_lines.append(get_line_text(view, lnum))
        for lnum in range(num_lines - head_count, num_lines):
            sampled_lines.append(get_line_text(view, lnum))

    while len(sampled_lines) and not len(sampled_lines[-1]):
        sampled_lines.pop()
    return sampled_lines


def guess_document_header(view, delim, policy):
    sampled_lines = sample_lines(view)
    if len(sampled_lines) < 10:
        return None
    header_line = sampled_lines[0]
    body_lines = sampled_lines[1:]
    sampled_records = [rainbow_utils.smart_split(l, delim, policy, False)[0] for l in body_lines]
    potential_header = rainbow_utils.smart_split(header_line, delim, policy, False)[0]
    has_header = rainbow_utils.guess_if_header(potential_header, sampled_records)
    return potential_header if has_header else None
        


def is_plain_text(view):
    syntax = view.settings().get('syntax')
    return syntax.find('Plain text.tmLanguage') != -1


def name_normalize(delim):
    # Same order as in https://stackoverflow.com/a/31976060/2898283
    name_map = dict()
    name_map['<'] = 'less-than'
    name_map['>'] = 'greater-than'
    name_map[':'] = 'colon'
    name_map['"'] = 'double-quote'
    name_map['/'] = 'slash'
    name_map['\\'] = 'backslash'
    name_map['|'] = 'pipe'
    name_map['?'] = 'question-mark'
    name_map['*'] = 'asterisk'
    name_map['\t'] = 'tab'
    name_map[' '] = 'space'
    if delim in name_map:
        return name_map[delim]
    return '[{}]'.format(delim)


def get_grammar_basename(delim, policy):
    if delim == '\t' and policy == 'simple':
        return 'TSV (Rainbow).tmLanguage'
    if delim == ',' and policy == 'quoted':
        return 'CSV (Rainbow).tmLanguage'
    simple_delims = '\t !"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~'
    standard_delims = '\t|,;'
    if policy == 'simple' and simple_delims.find(delim) == -1:
        return None
    if policy == 'quoted' and standard_delims.find(delim) == -1:
        return None
    policy_map = {'simple': 'Simple', 'quoted': 'Standard'}
    return 'Rainbow {} {}.tmLanguage'.format(name_normalize(delim), policy_map[policy])


def do_enable_rainbow(view, delim, policy):
    grammar_basename = get_grammar_basename(delim, policy)
    if grammar_basename is None:
        if policy == 'quoted':
            sublime.error_message('Error. Unable to use this character with "Standard" dialect. Try "Simple" instead.')
        else:
            sublime.error_message('Error. Unable to use this character as a separator.')
        return
    if view.settings().get('pre_rainbow_syntax', None) is None:
        pre_rainbow_syntax = view.settings().get('syntax') 
        view.settings().set('pre_rainbow_syntax', pre_rainbow_syntax)
        view.settings().set('rainbow_delim', delim)
        view.settings().set('rainbow_policy', policy)
    view.set_syntax_file('Packages/rainbow_csv/custom_grammars/{}'.format(grammar_basename))
    file_path = view.file_name()
    if file_path is not None:
        save_rainbow_params(file_path, delim, policy)


def do_disable_rainbow(view):
    pre_rainbow_syntax = view.settings().get('pre_rainbow_syntax', None)
    if pre_rainbow_syntax is None:
        return
    view.set_syntax_file(pre_rainbow_syntax)
    view.settings().erase('pre_rainbow_syntax')
    view.settings().erase('rainbow_delim')
    view.settings().erase('rainbow_policy')
    file_path = view.file_name()
    if file_path is not None:
        save_rainbow_params(file_path, 'disabled', '')


def enable_generic_command(view, policy):
    selection = view.sel()
    if len(selection) != 1:
        sublime.error_message('Error. Too many cursors/selections.')
        return
    region = selection[0]
    selection_text = view.substr(region)
    if len(selection_text) != 1:
        sublime.error_message('Error. Exactly one separator character should be selected.')
        return
    do_enable_rainbow(view, selection_text, policy)


class EnableStandardCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        enable_generic_command(self.view, 'quoted')


class EnableSimpleCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        enable_generic_command(self.view, 'simple')


class DisableCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        do_disable_rainbow(self.view)


def get_active_view():
    active_window = sublime.active_window()
    if not active_window:
        return None
    active_view = active_window.active_view()
    if not active_view:
        return None
    return active_view


def on_done(input_line):
    active_window = sublime.active_window()
    if not active_window:
        return
    active_view = active_window.active_view()
    if not active_view:
        return
    active_view.settings().set('rbql_mode', False)
    active_view.hide_popup()
    print( "input_line:", input_line) #FOR_DEBUG
    print( "rbql.__version__:", rbql.__version__) #FOR_DEBUG
    file_path = active_view.file_name()
    if not file_path:
        # TODO create a temp file from unnamed buffer
        sublime.error_message('Error. Unable to run query for this buffer')
        return
    # FIXME make rbql meta language configurable
    input_delim = active_view.settings().get('rainbow_delim')
    input_policy = active_view.settings().get('rainbow_policy')
    # FIXME make output delim and policy configurable
    output_delim = input_delim
    output_policy = input_policy
    query_result = sublime_rbql.converged_execute('python', file_path, input_line, input_delim, input_policy, output_delim, output_policy)
    error_type, error_details, warnings, dst_table_path = query_result
    if error_type is not None:
        sublime.error_message('{}. {}'.format(error_type, error_details))
        return
    if not dst_table_path or not os.path.exists(dst_table_path):
        sublime.error_message('Unknown Error: Unable to find destination file')
        return
    if warnings is not None and len(warnings):
        # FIXME TODO: test with multiple warnings
        warning_report = 'Warning!\n' + '\n'.join(warnings)
        sublime.message_dialog(warning_report)
    dst_view = active_window.open_file(dst_table_path)
    # FIXME for some reason we have infinite loop here:
    #while dst_view.is_loading():
    #    time.sleep(0.05)
    #do_enable_rainbow(dst_view, output_delim, output_policy)

def on_cancel():
    active_view = get_active_view()
    if not active_view:
        return
    active_view.settings().set('rbql_mode', False)
    active_view.hide_popup()


def show_column_names(view):
    cur_region = view.visible_region()
    line_regions = view.split_by_newlines(cur_region)
    middle_line = line_regions[len(line_regions) // 2]
    # FIXME use cursor line instead
    point = middle_line.a
    html_text = ''
    for i in range(10):
        #FIXME put column names in right positions
        html_text += '<span style="color:{}">a{}&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</span>'.format(rainbow_utils.color_entries[i % 10][1], i + 1)
    view.show_popup(html_text, location=point, max_width=1000)


class RunQueryCommand(sublime_plugin.TextCommand):
    #FIXME add context condition to F5 key in Default.sublime-keymap
    def run(self, edit):
        active_window = sublime.active_window()
        active_window.show_input_panel('Enter SQL-like RBQL query:', '', on_done, None, on_cancel)
        #FIXME we may still want to show regular hover in query mode, consider the case when there are lot of columns and query popup doesn't cover them all. So user will have to hover on them manually. You can restore the query hover from manual hover exit callback
        self.view.settings().set('rbql_mode', True)
        show_column_names(self.view)


def is_delimited_table(sampled_lines, delim, policy):
    if len(sampled_lines) < 2:
        return False
    num_fields = None
    for sl in sampled_lines:
        fields, warning = rainbow_utils.smart_split(sl, delim, policy, True)
        if warning or len(fields) < 2:
            return False
        if num_fields is None:
            num_fields = len(fields)
        if num_fields != len(fields):
            return False
    return True


def run_rainbow_init(view):
    if view.settings().get('rainbow_inited') is not None:
        return
    view.settings().set('rainbow_inited', True)
    file_path = view.file_name()
    if file_path is not None:
        delim, policy = load_rainbow_params(file_path)
        if delim == 'disabled':
            return
        if delim is not None:
            do_enable_rainbow(view, delim, policy)
            return
    if not is_plain_text(view):
        return
    sampled_lines = sample_lines(view)
    autodetection_dialects = [('\t', 'simple'), (',', 'quoted'), (';', 'quoted')]
    for delim, policy in autodetection_dialects:
        if is_delimited_table(sampled_lines, delim, policy):
            do_enable_rainbow(view, delim, policy)
            break


class RainbowAutodetectListener(sublime_plugin.EventListener):
    def on_load(self, view):
        run_rainbow_init(view)

    def on_activated(self, view):
        run_rainbow_init(view)


class RainbowHoverListener(sublime_plugin.ViewEventListener):
    @classmethod
    def is_applicable(cls, settings):
        return settings.get('rainbow_delim', None) is not None

    def on_hover(self, point, hover_zone):
        if self.view.settings().get('rbql_mode', False):
            return
        if hover_zone == sublime.HOVER_TEXT:
            delim = self.view.settings().get('rainbow_delim')
            policy = self.view.settings().get('rainbow_policy')
            if delim is None:
                return
            # lnum and cnum are 0-based
            lnum, cnum = self.view.rowcol(point)
            line_text = self.view.substr(self.view.line(point))
            hover_record, warning = rainbow_utils.smart_split(line_text, delim, policy, True)
            if warning or not len(hover_record):
                return
            field_num = rainbow_utils.get_field_by_line_position(hover_record, cnum)
            header = guess_document_header(self.view, delim, policy)
            ui_text = 'col# {}'.format(field_num + 1)
            if header is not None and len(header) == len(hover_record):
                column_name = header[field_num]
                ui_text += ', "{}"'.format(column_name)
            ui_hex_color = rainbow_utils.color_entries[field_num % 10][1]
            self.view.show_popup('<span style="color:{}">{}</span>'.format(ui_hex_color, ui_text), sublime.HIDE_ON_MOUSE_MOVE_AWAY, point)
