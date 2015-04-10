#!/usr/bin/env python3

''' convert csv files downloaded from an online banking account into qif format. '''

# The MIT License (MIT)
#
# Copyright (c) 2015 mx[replace-this]pycoder.nl
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import csv as _csv
import time as _time
import sys as _sys
import argparse as _argparse
import pprint as _pprint
import os as _os
from collections import namedtuple as _namedtuple
from collections import OrderedDict as _OrderedDict
from rules import rules
from types import MethodType

# the expected csv file format is defined here
# NOTE: this is not yet as generic as I would like it to be, so
#       when changing this, other parts of the code may have to be
#       changed as well for now...
HEADER = ["Date", "Description", "Original Description", "Amount", "Transaction Type",
          "Category", "Account Name", "Labels", "Notes"]
DELIMITER = ','
QUOTECHAR = '"'
LINETERMINATOR = '\r\n'
DATEFORMAT = '%m/%d/%Y'
CENTSEPARATOR = ','
WITHDRAWSTRING = 'debit'

# category for records that match none of the rules
UNKNOWN = 'unspecified'

# internal representation of parsed records
_record = _namedtuple('record',
                      'date namedesc description amount deposit_withdraw '
                      'code account labels notes'
)

# internal representation of a qif record
_qifrecord = _namedtuple('qifrecord', 'date, payee, amount, category, memo')


def write_qif(qrecs, f):
    f.write('!Type:Bank\n')
    for q in qrecs:
        f.write(formatqif(q))


def check_inputfile(fname):
    ''' validates properties of the given file and returns detected dialect.
    '''

    sniffer = _csv.Sniffer()
    errmsg = None

    with open(fname) as f:
        dialect = sniffer.sniff(f.read(1024))
        f.seek(0)

        if dialect.delimiter != DELIMITER:
            errmsg = 'detected delimiter {:s} != expected delimiter {:s}'
            errmsg = errmsg.format(repr(dialect.delimiter), repr(DELIMITER))

        if dialect.quotechar != QUOTECHAR:
            errmsg = 'detected quotechar {:s} != expected quotechar {:s}'
            errmsg = errmsg.format(repr(dialect.quotechar), repr(QUOTECHAR))

        if dialect.lineterminator != LINETERMINATOR:
            errmsg = 'detected line-ending {:s} != expected line-ending {:s}'
            errmsg = errmsg.format(repr(dialect.lineterminator),
                                   repr(LINETERMINATOR))

        f.seek(0)
        reader = _csv.reader(f, dialect)
        header = next(reader)
        if header != HEADER:
            errmsg = 'file should start with expected header {:s}'
            errmsg.format(repr(HEADER))

    if errmsg is not None:
        raise ValueError(errmsg)

    return dialect


def records(fname):
    ''' generates sequence of records from given filename.
    '''

    dialect = check_inputfile(fname)

    errmsg = 'date {:s} in line {:d} is not in expected format {:s}'

    with open(fname) as f:
        reader = _csv.reader(f, dialect)
        header = next(reader)
        lineno = 1
        for line in reader:
            rec = _record(*line)
            try:
                date = _time.strptime(rec.date, DATEFORMAT)
            except ValueError:
                raise ValueError(errmsg.format(rec.date, lineno, DATEFORMAT))
            lineno += 1
            yield rec


def rec2qif(rec):
    ''' converts a parsed record to a qif record. '''

    # convert the amount to float with proper sign
    sign = ''
    if rec.deposit_withdraw == WITHDRAWSTRING:
        sign = '-'
    amount = float(sign + rec.amount.replace(CENTSEPARATOR,'.'))
    amount = '{:.2f}'.format(amount)
    cat = category(rec)

    return _qifrecord(rec.date, rec.namedesc, amount, cat, rec.description)


def formatqif(qifrecord):
    ''' formats a qif record. '''

    qif = 'D{:s}\nT{:s}\nP{:s}\nL{:s}\nM{:s}\n^\n'
    qif = qif.format(qifrecord.date, qifrecord.amount, qifrecord.payee,
                     qifrecord.category, qifrecord.memo)
    return qif


def unknowns(records):
    ''' generates sequence of records that have unknown category. '''

    filtered = filter(lambda r: category(r) == UNKNOWN, records)
    for u in filtered:
        yield u


def convert(infile):
    ''' converts csv to qif. '''

    recs = records(infile)
    return (rec2qif(r) for r in recs)


def category(record):
    ''' checks for each field in the given record if any of the rules match.
    Returns corresponding category or the UNKNOWN category. Rules are processed
    in order and first match wins. '''

    for r in rules:
        # collect the fieldnames of the fields that are defined
        tomatch = [f for f in r._fields if getattr(r, f) is not None and f != 'category']
        # and their corresponding value
        matchvalues = [getattr(r, f) for f in tomatch if f != 'category']
        # and the values in these fields in the record
        recordvalues = [getattr(record, f) for f in tomatch]
        # these should be of equal length
        if len(matchvalues) != len(recordvalues):
            raise RuntimeError('bug: matchvalues and recordvalues len mismatch')
        # check if matchvalues occur as substring of recordvalues
        matches = map(lambda a,b: a in b, matchvalues, recordvalues)
        # condense to a set of booleans
        matches = set([m for m in matches])
        # if all are true, we have a full match
        if len(matches) == 1 and matches == set([True]):
            return r.category
    # if we get here, return UNKNOWN category
    return UNKNOWN


def _cli():
    ''' command line interface. '''
    parser = _argparse.ArgumentParser(
        formatter_class = _argparse.RawDescriptionHelpFormatter,
        description = 'convert csv files from your bank account to QIF format.',
        epilog = 'example usage: \n yac2qc.py -o statements.qif statements.csv '
                 '\n yac2qc.py -u statements.csv'
                 '\n\nconfiguration: \n define your own category rules in rules.py')
    parser.add_argument('infile', metavar ='INFILE',
        help = 'csv file to convert')
    parser.add_argument('-o', metavar = 'OUTFILE',
        help = 'destination file')
    parser.add_argument('-u', action='store_true',
        help = 'print records for which category is unknown.')
    args = parser.parse_args()
    return args


def print_unknowns(fname):
    ''' prints the transactions for which none of the category rules match. 
    '''

    recs = records(fname)
    unks = unknowns(recs)

    for u in unks:
        _pprint.pprint(u._asdict())


def _main():
    args = _cli()

    if args.u:
        return print_unknowns(args.infile)

    qif_records = convert(args.infile)

    if args.o is not None:
        with open(args.o, 'wt') as f:
            write_qif(qif_records, f)
    else:
        write_qif(qif_records, _sys.stdout)


if __name__ == "__main__":
    _main()
