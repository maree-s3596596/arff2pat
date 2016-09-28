#!/usr/bin/env python

"""
Converts ARFF (weka) files into .pat (javanns) files

Each nominal attribute and class label is mapped to a N-width binary string
  where N is the number of possible values for that attribute/class label.
Numeric attributes are used as input directly.
Numerical class labels are scaled to [0,1]

If discardmissing is given as a yes-like value (e.g. YES, Y, yes, y, true, TRUE),
then numerical values that are missing are set to 0 and nominal values that 
are missing are set to a N-width binary string (where N is the number of
possible values for that attribute) set to all zeros.

Usage:
chmod u+x arff2pat.py
./arff2pat.py

Without command line arguments, it will prompt you for inputs
Otherwise, see ./arff2pat.py --help for information

Refer to https://github.com/maree-s3596596/arff2pat/blob/master/README.md for
more information

"""

import click
import numpy as np
from sklearn.cross_validation import train_test_split
from sklearn.preprocessing import MinMaxScaler

PAT_FILE_CONTENT = """SNNS pattern definition file V3.2
generated at Mon Apr 25 15:58:23 1994

No. of patterns : {data_length}
No. of input units : {inputs}
No. of output units : {outputs}
{data}
"""

NUMERIC_ATTRIBUTE_TYPES = ['real','REAL','numeric','NUMERIC']

def encode_nominal(num_values, flag_index):
    """
    Encodes a nominal variable as a binary string
    Sets the "bit" for the nominal value 
    If the flag_index passed is -1, its a missing value 
    encoding, so just returns all zeros
    """
    code = ['0'] * num_values  # init
    if flag_index >= 0:
        code[flag_index] = '1'
    return " ".join(code)

@click.command()
@click.option('--arff', prompt='ARFF file', help='The input ARFF file')
@click.option('--pat', prompt='Output pat file', help='The output PAT file')
@click.option('--testsize', prompt='Test set size float between 0.0,1.0',
              help='The size of the test set as float between 0.0,1.0',
              default=0.33)
@click.option('--validationsize',
              prompt='Validation set size (between 0.0,1.0)',
              help='The size of the validation set as float between 0.0,1.0',
              default=0.33)
@click.option('--discardmissing',
              prompt='Whether to discard missing values',
              help='Whether to discard missing values as yes or no',
              default='yes')
def convert(arff, pat, testsize, validationsize, discardmissing):
    """
    Converts arff file to pat file for moving data
    between weka and javanns
    """

    if discardmissing.upper() in ['YES','Y','T','TRUE']:
        discardmissing = True
    else: 
        discardmissing = False
    testsize = float(testsize)
    validationsize = float(validationsize)
    outputs = 0  # number of output attributes (n-width)
    attributes = []  # we assume the last output-n-attributes is alwys the class
    data_found = False
    data = []
    rows_with_missing_data = 0

    # process arff file contents
    with open(arff) as infile:

        line_num = 0
        for line in infile:
            line_num += 1
            # ignore comments
            if line.strip().startswith('%'):
                continue
            # if we're in the data section
            if data_found:
                # ignore lines with missing values
                if '?' in line and discardmissing:
                    rows_with_missing_data += 1
                else:
                    data.append(line.strip())
                continue
            # if we're dealing with an attribute definition
            if line.upper().startswith("@ATTRIBUTE"):
                attr = {}
                # if its numeric we can just use the values straight
                # (we will deal with scaling numeric class later on)
                if any(t in line for t in NUMERIC_ATTRIBUTE_TYPES):
                    values = line.split()
                    attr['name'] = values[1].strip()
                    attr['type'] = values[2].strip().upper()
                    attr['values'] = [{}]
                    # neural network missing value encoding
                    attr['nn_missing'] = '0'
                    outputs = 1
                # else if the line contains { it is nominal so we need to encode
                # into an N-length string binary form
                elif '{' in line:
                    line = line.strip()
                    categories = line[line.index('{')+1:-1]
                    categories = categories.split(',')
                    attr['name'] = line.split(' ')[1]
                    attr['type'] = 'NOMINAL'
                    attr['values'] = []
                    i = 0
                    for category in categories:
                        attr['values'].append({ 'code': i,
                                                'orig': category.strip() })
                        i += 1
                    outputs = i
                    # neural network missing values encoding
                    attr['nn_missing'] = encode_nominal(outputs, -1) 
                    
                    for dic in attr['values']:
                        dic['code'] = encode_nominal(outputs, dic['code'])
                attributes.append(attr)

            # if we've found the data section, set data_found flag
            if line.upper().startswith("@DATA"):
                data_found = True
                continue

    # encode the data
    encoded_data = []
    inputs = sum([len(attr['values']) for attr in attributes]) - outputs

    encode_missing_messages = {}

    ## encode data
    for d in data:
        fields = d.split(',')
        for i in range(0, len(fields)):
            if attributes[i]['type'] == 'NOMINAL':
                for code in attributes[i]['values']:
                    # if missing values aren't discarded and this is a missing
                    if not discardmissing and fields[i] == '?':
                        # encode it with the appropriate missing code
                        # as set earlier
                        orig = fields[i]
                        fields[i] = attributes[i]['nn_missing']
                        if i in encode_missing_messages:
                            encode_missing_messages[i]['count'] = \
                              encode_missing_messages[i]['count'] + 1
                        else:
                            encode_missing_messages[i] = {}
                            encode_missing_messages[i]['code'] = fields[i]
                            encode_missing_messages[i]['orig'] = orig
                            encode_missing_messages[i]['count'] = 1
                    elif fields[i] == code['orig']:
                        fields[i] = code['code']

        encoded_data.append(fields)

    # if class variable is numeric, scale [0,1]
    if attributes[-1]['type'] != 'NOMINAL':
        encoded_data_np = np.array(encoded_data)
        class_vars = encoded_data_np[:,-1]
        min_max_scaler = MinMaxScaler()
        scaled_class_vars = min_max_scaler.fit_transform(class_vars.reshape(-1,1))
        encoded_data_np[:,-1] = scaled_class_vars.reshape(len(class_vars))
        encoded_data = encoded_data_np.tolist()

    if testsize > 0.0:

        do_validation_split = (validationsize > 0.0)

        arr = np.array(encoded_data)
        X, y = (arr[:,:-1], arr[:,-1])
        X_train, X_test, y_train, y_test = train_test_split(X, y,
                                                            test_size=testsize)
        # further split your train into validation if required
        if do_validation_split:
            X_train, X_valid, y_train, y_valid = \
                train_test_split(X_train, y_train,
                                test_size=validationsize)

        train = np.append(X_train, y_train.reshape(len(y_train),1),1)
        if do_validation_split:
            valid = np.append(X_valid, y_valid.reshape(len(y_valid),1),1)
        test = np.append(X_test, y_test.reshape(len(y_test),1),1)

        train_len = len(train)
        train = [" ".join(row) for row in train]
        train = "\n".join(train)

        if do_validation_split:
            valid_len = len(valid)
            valid = [" ".join(row) for row in valid]
            valid = "\n".join(valid)

        test_len = len(test)
        test = [" ".join(row) for row in test]
        test = "\n".join(test)

        train_file = pat.replace('.pat', '-train.pat')
        with open(train_file,'w') as outfile:
            outfile.write(PAT_FILE_CONTENT.format(data_length=train_len,
                                                  inputs=inputs,
                                                  outputs=outputs,
                                                  data=train))
        print("\n\nFile output to: %s (%d cases)" % (train_file, train_len))

        if do_validation_split:
            valid_file = pat.replace('.pat', '-valid.pat')
            with open(valid_file,'w') as outfile:
                outfile.write(PAT_FILE_CONTENT.format(data_length=valid_len,
                                                      inputs=inputs,
                                                      outputs=outputs,
                                                      data=valid))
            print("\n\nFile output to: %s (%d cases)" % (valid_file, valid_len))

        test_file = pat.replace('.pat', '-test.pat')
        with open(test_file, 'w') as outfile:
            outfile.write(PAT_FILE_CONTENT.format(data_length=test_len,
                                                  inputs=inputs,
                                                  outputs=outputs,
                                                  data=test))
        print("\n\nFile output to: %s (%d cases)" % (test_file, test_len))

    else: # no splitting required
        data_length = len(encoded_data)
        with open(pat, 'w') as outfile:
            encoded_data = "\n".join(encoded_data)
            outfile.write(PAT_FILE_CONTENT.format(data_length=data_length,
                                                  inputs=inputs,
                                                  outputs=outputs,
                                                  data=encoded_data))

        print("\n\nFile output to: %s" % pat)

    if rows_with_missing_data == 0 and not(encode_missing_messages):
        print("\nNo missing values were detected")
    elif discardmissing:
        print("\nDiscarded %d cases with missing data" % rows_with_missing_data)
    
    print("\nNumber of inputs: %d" % inputs)
    print("\nNumber of outputs: %d" % outputs)
    print("\nAttribute encoding (the last listed is the class label)")

    # print out encodings
    idx = -1
    for attribute in attributes:
        idx += 1
        print(attribute['name'])
        if attribute['type'] == 'NOMINAL':
            for value in attribute['values']:
                    print("\t%s -> %s" % (value['orig'], value['code']))
        else:
            print("\t%s" % attribute['type'])
        if idx in encode_missing_messages:
            dic = encode_missing_messages[idx]
            print("\t%s -> %s (%d cases)" % (dic['orig'], dic['code'], dic['count']))

if __name__ == '__main__':
    convert()
