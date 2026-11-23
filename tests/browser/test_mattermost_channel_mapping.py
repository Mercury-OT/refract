"""Exercise the pilot's page mapping in Chromium with synthetic channel rows."""

import pytest
from playwright.sync_api import sync_playwright

from examples.mattermost_api.channel_page import _READ_CHANNEL


OLD_ID = "a" * 26
NEW_ID = "b" * 26
GROUP_ID = "user-activity-" + "c" * 26 + "_" + "d" * 26


def wrapper(element):
    return f'<div class="item_measurer"><div class="post-row__padding">{element}</div></div>'


def card(identity, message, *, system=False):
    system_class = " post--system" if system else ""
    return f"""
      <div data-testid="postView" class="post{system_class}" id="post_{identity}">
        <div data-testid="postContent" class="post__content">
          <div>
            <div class="post__header">
              <div><a class="post__permalink" id="CENTER_time_{identity}"><time>10:00</time></a></div>
            </div>
            <div data-testid="post-body" class="post__body" id="{identity}_message">
              <div data-testid="post-message-text" class="post-message__text"
                   id="postMessageText_{identity}">{message}</div>
            </div>
          </div>
        </div>
      </div>"""


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True)
        try:
            yield browser
        finally:
            browser.close()


@pytest.fixture
def page(browser):
    page = browser.new_page()
    try:
        yield page
    finally:
        page.close()


def snapshot(page, *elements):
    intro = '<div id="channelIntro" class="channel-intro">Channel information</div>'
    date = '<div class="Separator BasicSeparator" data-testid="basicSeparator">Today</div>'
    rows = "".join(wrapper(row) for row in (intro, date, *elements))
    page.set_content(f"""
      <div id="post-list" role="main"><div id="postListContent">
        <div id="postListScrollContainer"><div class="innerList">{rows}</div></div>
      </div></div>
      <div id="create_post"><textarea id="post_textbox"></textarea></div>""")
    return page.evaluate(_READ_CHANNEL)


def test_identified_posts_remain_distinct_from_grouped_activity(page):
    result = snapshot(page, card(OLD_ID, "Friday delivery"),
                      card(GROUP_ID, "Members joined", system=True),
                      card(NEW_ID, "Friday delivery"))
    posts = result["channel.posts"]
    assert [p["id"] for p in posts["identified"]] == [OLD_ID, NEW_ID]
    assert [p["fields"]["message"] for p in posts["identified"]] == ["Friday delivery"] * 2
    assert posts["anonymous"] == []
    assert result["channel.view"]["anonymous"][0]["fields"]["grouped_activity_count"] == 1


def test_duplicate_post_identity_is_observable(page):
    result = snapshot(page, card(NEW_ID, "First body"), card(NEW_ID, "Second body"))
    posts = result["channel.posts"]["identified"]
    assert [(p["id"], p["fields"]["message"]) for p in posts] == [
        (NEW_ID, "First body"), (NEW_ID, "Second body")]


def assert_unknown_or_incomplete(result):
    if result is not False:
        assert len(result["channel.posts"]["anonymous"]) == 1
        assert result["channel.view"]["anonymous"][0]["fields"]["grouped_activity_count"] == 0


@pytest.mark.parametrize(("old", "new"), [
    ('class="post post--system"', 'class="post"'),
    ('id="postMessageText_' + GROUP_ID + '"', 'id="postMessageText_other"'),
    ('id="CENTER_time_' + GROUP_ID + '"', 'id="CENTER_time_other"'),
    ('id="' + GROUP_ID + '_message"', 'id="other_message"'),
    ('data-testid="postContent"', 'data-testid="other"'),
    ('data-testid="post-body"', 'data-testid="other"'),
    ("d" * 26, "c" * 26),
    ("c" * 26, "c" * 25),
], ids=["ordinary-card", "text-id", "permalink", "body-id", "content", "body",
        "repeated-component", "short-component"])
def test_incomplete_group_signature_remains_unverified(page, old, new):
    good = card(GROUP_ID, "Members joined", system=True)
    assert old in good
    assert_unknown_or_incomplete(snapshot(page, good.replace(old, new)))


@pytest.mark.parametrize("nested", [
    '<div class="Separator BasicSeparator" data-testid="basicSeparator">Today</div>',
    '<div id="channelIntro" class="channel-intro">Channel information</div>',
    card(GROUP_ID, "Members joined", system=True),
    card(OLD_ID, "Friday delivery"),
], ids=["separator", "intro", "grouped-activity", "regular-post"])
def test_unrecognized_row_cannot_borrow_nested_markup(page, nested):
    assert_unknown_or_incomplete(snapshot(page, f"<article>Unknown row<div>{nested}</div></article>"))


def test_message_markup_cannot_replace_the_group_permalink(page):
    fake_permalink = f'<a class="post__permalink" id="CENTER_time_{GROUP_ID}">10:00</a>'
    grouped = card(GROUP_ID, "Members joined " + fake_permalink, system=True)
    grouped = grouped.replace(f'id="CENTER_time_{GROUP_ID}"', 'id="invalid-header-id"', 1)
    assert_unknown_or_incomplete(snapshot(page, grouped))


def test_group_with_three_distinct_members_is_counted_once(page):
    compound = GROUP_ID + "_" + "e" * 26
    result = snapshot(page, card(compound, "Membership changes", system=True))
    assert result["channel.view"]["anonymous"][0]["fields"]["grouped_activity_count"] == 1
    assert result["channel.posts"] == {"identified": [], "anonymous": []}


def test_group_header_and_message_must_share_a_container(page):
    grouped = card(GROUP_ID, "Membership changes", system=True)
    grouped = grouped.replace('<div data-testid="post-body"', '</div><div><div data-testid="post-body"')
    assert_unknown_or_incomplete(snapshot(page, grouped))


@pytest.mark.parametrize("operation", ["remove", "duplicate"])
def test_complete_snapshot_requires_one_real_intro(page, operation):
    snapshot(page, card(OLD_ID, "One post"))
    page.locator("#channelIntro").evaluate("""(intro, operation) => {
        const wrapper = intro.closest('.item_measurer');
        if (operation === 'remove') wrapper.remove();
        else wrapper.after(wrapper.cloneNode(true));
    }""", operation)
    assert page.evaluate(_READ_CHANNEL) is False


@pytest.mark.parametrize("selector", [".innerList", ".item_measurer", ".item_measurer > div"])
def test_nonempty_text_outside_recognized_row_makes_snapshot_incomplete(page, selector):
    snapshot(page, card(NEW_ID, "Friday delivery"))
    page.locator(selector).first.evaluate("node => node.prepend(document.createTextNode('Unknown row'))")
    assert page.evaluate(_READ_CHANNEL) is False
