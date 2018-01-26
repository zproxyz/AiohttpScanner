#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import os


class FileHelper:
    @staticmethod
    def load_config(path_file):
        with open(path_file) as json_data_file:
            data = json.load(json_data_file)
        return data

    @staticmethod
    def get_line(path_file, offset=0):
        with open(path_file) as file:
            for i, line in enumerate(file):
                if offset != 0 and i < offset:
                    continue
                yield line.strip(), i

    @staticmethod
    def put_line(path_file):
        with open(path_file, 'a') as file:
            while True:
                line = yield
                if line is 'Close':
                    break
                file.write(line + '\n')
                file.flush()
                os.fsync(file.fileno())
        yield ([])

    @staticmethod
    def save_stats(path_file, data):
        with open(path_file, 'w') as outfile:
            json.dump(data, outfile)
