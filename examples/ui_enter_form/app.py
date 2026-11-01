"""Ordinary same-page form search, sharing the fixed public search service.

The page owns native validation and its submit handlers cancel navigation.
There is no Refract import, expected result, or adapter preparation here.
"""
from html import escape
from pathlib import Path

from examples.ui_enter_search.app import Application as SearchApplication


class Application(SearchApplication):
    def page(self):
        rows = "".join("<li>" + escape(record["name"]) + "</li>" for record in self.records)
        return ('<!doctype html><html lang="en"><meta charset="utf-8">'
                '<title>Search records</title><h1>Search records</h1>'
                '<form id="search-form" action="/search" method="get">'
                '<label for="search">Name contains</label>'
                '<input id="search" type="search" name="q" required>'
                '<button id="search-submit" type="submit">Search</button></form>'
                '<p>Press Enter to search.</p><ul id="records" aria-label="Search results">'
                + rows + '</ul><p id="notice" role="status"></p>'
                + f'<script src="/{self.implementation}.js"></script></html>').encode()

    def script(self, name):
        return Path(__file__).with_name(name).read_bytes()
