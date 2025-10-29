"""
Wikidotフォーラムのスレッドを扱うモジュール

このモジュールは、Wikidotサイトのフォーラムスレッドに関連するクラスや機能を提供する。
スレッドの情報取得や閲覧などの操作が可能。
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from bs4 import BeautifulSoup, NavigableString

from ..common.exceptions import NoElementException
from ..util.parser import odate as odate_parser
from ..util.parser import user as user_parser

if TYPE_CHECKING:
    from .forum_category import ForumCategory
    from .forum_post import ForumPost, ForumPostCollection
    from .page import Page
    from .site import Site
    from .user import AbstractUser


class ForumThreadCollection(list["ForumThread"]):
    """
    フォーラムスレッドのコレクションを表すクラス

    複数のフォーラムスレッドを格納し、一括して操作するためのリスト拡張クラス。
    特定のカテゴリ内のスレッド一覧を取得する機能などを提供する。
    """

    def __init__(
        self,
        site: Optional["Site"] = None,
        threads: Optional[list["ForumThread"]] = None,
    ):
        """
        初期化メソッド

        Parameters
        ----------
        site : Site | None, default None
            スレッドが属するサイト。Noneの場合は最初のスレッドから推測する
        threads : list[ForumThread] | None, default None
            格納するスレッドのリスト
        """
        super().__init__(threads or [])

        if site is not None:
            self.site = site
        else:
            self.site = self[0].site

    def __iter__(self) -> Iterator["ForumThread"]:
        """
        コレクション内のスレッドを順に返すイテレータ

        Returns
        -------
        Iterator[ForumThread]
            スレッドオブジェクトのイテレータ
        """
        return super().__iter__()

    def find(self, id: int) -> Optional["ForumThread"]:
        """
        指定したIDのスレッドを取得する

        Parameters
        ----------
        id : int
            取得するスレッドのID

        Returns
        -------
        ForumThread | None
            指定したIDのスレッド。存在しない場合はNone
        """
        for thread in self:
            if thread.id == id:
                return thread
        return None

    @staticmethod
    def _parse_list_in_category(
        site: "Site", html: BeautifulSoup, category: Optional["ForumCategory"] = None
    ) -> "ForumThreadCollection":
        """
        フォーラムページのHTMLからスレッド情報を抽出する内部メソッド

        HTMLからスレッドのタイトル、説明、作成者、作成日時などの情報を抽出し、
        ForumThreadオブジェクトのリストを生成する。

        Parameters
        ----------
        site : Site
            スレッドが属するサイト
        html : BeautifulSoup
            パース対象のHTML
        category : ForumCategory | None, default None
            スレッドが属するカテゴリ（オプション）

        Returns
        -------
        list[ForumThread]
            抽出されたスレッドオブジェクトのリスト

        Raises
        ------
        NoElementException
            必要なHTML要素が見つからない場合
        """
        threads = []
        for info in html.select("table.table tr.head~tr"):
            title = info.select_one("div.title a")
            if title is None:
                raise NoElementException("Title element is not found.")

            title_href = title.get("href")
            if title_href is None:
                raise NoElementException("Title href is not found.")

            thread_id_match = re.search(r"t-(\d+)", str(title_href))
            if thread_id_match is None:
                raise NoElementException("Thread ID is not found.")

            thread_id = int(thread_id_match.group(1))

            description_elem = info.select_one("div.description")
            user_elem = info.select_one("span.printuser")
            odate_elem = info.select_one("span.odate")
            posts_count_elem = info.select_one("td.posts")

            if description_elem is None:
                raise NoElementException("Description element is not found.")
            if user_elem is None:
                raise NoElementException("User element is not found.")
            if odate_elem is None:
                raise NoElementException("Odate element is not found.")
            if posts_count_elem is None:
                raise NoElementException("Posts count element is not found.")

            thread = ForumThread(
                site=site,
                id=int(thread_id),
                title=title.text,
                description=description_elem.text,
                created_by=user_parser(site.client, user_elem),
                created_at=odate_parser(odate_elem),
                post_count=int(posts_count_elem.text),
                category=category,
            )

            threads.append(thread)

        return ForumThreadCollection(site=site, threads=threads)

    @staticmethod
    def _parse_thread_page(
        site: "Site", html: BeautifulSoup, category: Optional["ForumCategory"] = None
    ) -> "ForumThread":
        """
        スレッドページのHTMLからスレッド情報を抽出する内部メソッド

        HTMLからスレッドのタイトル、説明、作成者、作成日時などの情報を抽出し、
        ForumThreadオブジェクトを生成する。

        Parameters
        ----------
        site : Site
            スレッドが属するサイト
        html : BeautifulSoup
            パース対象のHTML
        category : ForumCategory | None, default None
            スレッドが属するカテゴリ（オプション）

        Returns
        -------
        ForumThread
            抽出されたスレッドオブジェクト

        Raises
        ------
        NoElementException
            必要なHTML要素が見つからない場合
        """
        # title取得処理
        # forum-breadcrumbsの最後のNavigableStringを取得
        bc_elem = html.select_one("div.forum-breadcrumbs")
        if bc_elem is None:
            raise NoElementException("Breadcrumbs element is not found.")
        title = bc_elem.contents[-1].text.strip().removeprefix("» ")

        # description取得処理
        description_block_elem = html.select_one("div.description-block")
        if description_block_elem is None:
            raise NoElementException("Description block element is not found.")
        description = "".join(
            [text.strip() for text in description_block_elem if isinstance(text, NavigableString) and text.strip()]
        )

        # created_by取得処理
        user_elem = html.select_one("div.statistics span.printuser")
        if user_elem is None:
            raise NoElementException("User element is not found.")
        created_by = user_parser(site.client, user_elem)

        # created_at取得処理
        odate_elem = html.select_one("div.statistics span.odate")
        if odate_elem is None:
            raise NoElementException("Odate element is not found.")
        created_at = odate_parser(odate_elem)

        # post_count取得処理
        # 3番目のbrの前のテキスト
        br_tags = html.select("div.statistics br")
        if len(br_tags) < 3:
            raise NoElementException("Br tags are not enough.")
        post_count_elem = br_tags[2].previous_sibling
        if post_count_elem is None:
            raise NoElementException("Posts count element is not found.")
        post_count_text = str(post_count_elem)
        post_count_match = re.search(r"(\d+)", post_count_text)
        if post_count_match is None:
            raise NoElementException("Post count is not found.")
        post_count = int(post_count_match.group(1))

        # id取得処理
        # WIKIDOT.forumThreadId = xxxxxx;を全体から検索
        script_elem = html.find("script", text=re.compile(r"WIKIDOT.forumThreadId = \d+;"))
        if script_elem is None:
            raise NoElementException("Script element is not found.")
        thread_id_match = re.search(r"(\d+)", script_elem.text)
        if thread_id_match is None:
            raise NoElementException("Thread ID is not found in script.")
        thread_id = int(thread_id_match.group(1))

        # Retrieve page_fullname
        # Get related page from description-block
        page_fullname = None
        if description_block_elem is not None:
            # Find all links that start with / but not forum/ or feed/
            page_links = description_block_elem.select("a[href^='/']")
            for page_link in page_links:
                page_href = page_link.get("href", "")
                # Remove leading slash
                page_fullname_candidate = str(page_href).removeprefix("/")
                # Only set if it's not a forum/feed/javascript link
                if not page_fullname_candidate.startswith("forum") and not page_fullname_candidate.startswith("feed"):
                    page_fullname = page_fullname_candidate
                    break

        return ForumThread(
            site=site,
            id=thread_id,
            title=title,
            description=description,
            created_by=created_by,
            created_at=created_at,
            post_count=post_count,
            category=category,
            page_fullname=page_fullname,
        )

    @staticmethod
    def acquire_all_in_category(category: "ForumCategory") -> "ForumThreadCollection":
        """
        特定のカテゴリ内のすべてのスレッドを取得する

        カテゴリページの各ページにアクセスし、すべてのスレッド情報を収集する。
        ページネーションが存在する場合は、すべてのページを巡回する。

        Parameters
        ----------
        category : ForumCategory
            スレッドを取得するカテゴリ

        Returns
        -------
        ForumThreadCollection
            カテゴリ内のすべてのスレッドを含むコレクション

        Raises
        ------
        NoElementException
            HTML要素の解析に失敗した場合
        """
        threads: list["ForumThread"] = []

        first_response = category.site.amc_request(
            [
                {
                    "p": 1,
                    "c": category.id,
                    "moduleName": "forum/ForumViewCategoryModule",
                }
            ]
        )[0]

        first_body = first_response.json()["body"]
        first_html = BeautifulSoup(first_body, "lxml")

        threads.extend(ForumThreadCollection._parse_list_in_category(category.site, first_html))

        # pager検索
        pager = first_html.select_one("div.pager")
        if pager is None:
            return ForumThreadCollection(site=category.site, threads=threads)

        last_page = int(pager.select("a")[-2].text)
        if last_page == 1:
            return ForumThreadCollection(site=category.site, threads=threads)

        responses = category.site.amc_request(
            [
                {
                    "p": page,
                    "c": category.id,
                    "moduleName": "forum/ForumViewCategoryModule",
                }
                for page in range(2, last_page + 1)
            ]
        )

        for response in responses:
            body = response.json()["body"]
            html = BeautifulSoup(body, "lxml")
            threads.extend(ForumThreadCollection._parse_list_in_category(category.site, html, category))

        return ForumThreadCollection(site=category.site, threads=threads)

    @staticmethod
    def acquire_from_thread_ids(
        site: "Site", thread_ids: list[int], category: Optional["ForumCategory"] = None
    ) -> "ForumThreadCollection":
        """
        指定されたスレッドIDのスレッド情報を取得する

        指定されたスレッドIDのスレッド情報を取得し、コレクションとして返す。

        Parameters
        ----------
        site : Site
            スレッドが属するサイト
        thread_ids : list[int]
            取得するスレッドのIDリスト
        category : ForumCategory | None, default None
            スレッドが属するカテゴリ（オプション）

        Returns
        -------
        ForumThreadCollection
            取得したスレッド情報のコレクション
        """
        responses = site.amc_request(
            [
                {
                    "t": thread_id,
                    "moduleName": "forum/ForumViewThreadModule",
                }
                for thread_id in thread_ids
            ]
        )

        threads = []

        for response, thread_id in zip(responses, thread_ids):
            body = response.json()["body"]
            html = BeautifulSoup(body, "lxml")

            thread = ForumThreadCollection._parse_thread_page(site, html, category)
            if thread_id != thread.id:
                raise NoElementException("Thread ID is not matched.")
            threads.append(thread)

        return ForumThreadCollection(site=site, threads=threads)


@dataclass
class ForumThread:
    """
    Wikidotフォーラムのスレッドを表すクラス

    フォーラムスレッドの基本情報を保持する。スレッドのタイトル、説明、
    作成者、作成日時、投稿数などの情報を提供する。

    Attributes
    ----------
    site : Site
        スレッドが属するサイト
    id : int
        スレッドID
    title : str
        スレッドのタイトル
    description : str
        スレッドの説明または抜粋
    created_by : AbstractUser
        スレッドの作成者
    created_at : datetime
        スレッドの作成日時
    post_count : int
        スレッド内の投稿数
    category : ForumCategory | None, default None
        スレッドが属するフォーラムカテゴリ
    page_fullname : str | None, default None
        Full name of the page associated with this thread
    _page : Page | None, default None
        Page object associated with this thread (lazy loaded)
    """

    site: "Site"
    id: int
    title: str
    description: str
    created_by: "AbstractUser"
    created_at: datetime
    post_count: int
    category: Optional["ForumCategory"] = None
    page_fullname: Optional[str] = None
    _page: Optional["Page"] = None

    def __str__(self):
        """
        オブジェクトの文字列表現

        Returns
        -------
        str
            スレッドの文字列表現
        """
        return (
            f"ForumThread(id={self.id}, "
            f"title={self.title}, description={self.description}, "
            f"created_by={self.created_by}, created_at={self.created_at}, "
            f"post_count={self.post_count}), "
            f"category={self.category}"
        )

    @property
    def url(self) -> str:
        """
        スレッドのURLを取得する

        Returns
        -------
        str
            スレッドのURL
        """
        return f"{self.site.url}/forum/t-{self.id}/"

    @property
    def page(self) -> Optional["Page"]:
        """
        Get the page associated with this thread.

        Returns:
            Page | None: The associated page object, or None if no page is associated.
        """
        from .page import PageCollection, SearchPagesQuery

        if self._page is None and self.page_fullname is not None:
            # Fetch the page
            pages = PageCollection.search_pages(self.site, SearchPagesQuery(fullname=self.page_fullname))
            if len(pages) > 0:
                self._page = pages[0]
        return self._page

    @page.setter
    def page(self, value: Optional["Page"]):
        """
        Set the associated page.

        Args:
            value: The page object to set.
        """
        self._page = value
        if value is not None:
            self.page_fullname = value.fullname

    @staticmethod
    def get_from_id(site: "Site", thread_id: int, category: Optional["ForumCategory"] = None) -> "ForumThread":
        """
        スレッドIDからスレッド情報を取得する

        Parameters
        ----------
        site : Site
            スレッドが属するサイト
        thread_id : int
            取得するスレッドのID
        category : ForumCategory | None, default None
            スレッドが属するカテゴリ（オプション）

        Returns
        -------
        ForumThread
            取得したスレッド情報
        """
        return ForumThreadCollection.acquire_from_thread_ids(site, [thread_id], category)[0]

    def get_posts(self, page: int = 1) -> "ForumPostCollection":
        """
        Get posts from this thread.

        Args:
            page: Page number (1-indexed). Defaults to 1.

        Returns:
            ForumPostCollection: Collection of forum posts.

        Raises:
            NoElementException: If required elements are not found in response.
        """
        from .forum_post import ForumPost, ForumPostCollection

        response = self.site.amc_request(
            [
                {
                    "t": self.id,
                    "pageNo": page,
                    "moduleName": "forum/ForumViewThreadModule",
                }
            ]
        )[0]

        body = response.json()["body"]
        html = BeautifulSoup(body, "lxml")

        posts = []
        for post_elem in html.select("div.post"):
            post_id_elem = post_elem.get("id")
            if post_id_elem is None:
                continue

            post_id_str = str(post_id_elem).removeprefix("post-")
            if not post_id_str.isdigit():
                continue
            post_id = int(post_id_str)

            # Find the parent post-container
            post_container = post_elem.parent

            # Get title
            title_elem = post_container.select_one("div.title")
            title = title_elem.text.strip() if title_elem else ""

            # Get text
            text_elem = post_container.select_one("div.content")
            text = str(text_elem) if text_elem else ""

            # Get created_by
            user_elem = post_container.select_one("div.info span.printuser")
            if user_elem is None:
                raise NoElementException("User element is not found.")
            created_by = user_parser(self.site.client, user_elem)

            # Get created_at
            odate_elem = post_container.select_one("div.info span.odate")
            if odate_elem is None:
                raise NoElementException("Odate element is not found.")
            created_at = odate_parser(odate_elem)

            # Get edited info if exists
            edited_by = None
            edited_at = None
            edit_info_elem = post_container.select_one("div.changes")
            if edit_info_elem:
                edited_user_elem = edit_info_elem.select_one("span.printuser")
                edited_odate_elem = edit_info_elem.select_one("span.odate")
                if edited_user_elem and edited_odate_elem:
                    edited_by = user_parser(self.site.client, edited_user_elem)
                    edited_at = odate_parser(edited_odate_elem)

            # Get parent post ID if exists
            # Check if this post-container is nested inside another post-container
            parent_post_id = None
            if post_container is not None:
                # Find parent post-container by looking for ancestor with class post-container
                parent_container = post_container.find_parent("div", class_="post-container")
                if parent_container is not None:
                    parent_container_id = parent_container.get("id")
                    if parent_container_id:
                        # Extract parent post ID from fpc-XXXXXX format
                        parent_id_str = str(parent_container_id).removeprefix("fpc-")
                        if parent_id_str.isdigit():
                            parent_post_id = int(parent_id_str)

            post = ForumPost(
                thread=self,
                id=post_id,
                title=title,
                text=text,
                element=post_elem,
                created_by=created_by,
                created_at=created_at,
                edited_by=edited_by,
                edited_at=edited_at,
                _parent_id=parent_post_id,
            )

            posts.append(post)

        return ForumPostCollection(thread=self, posts=posts)

    def get_all_posts(self) -> "ForumPostCollection":
        """
        Get all posts from this thread across all pages.

        Returns:
            ForumPostCollection: Collection of all forum posts in this thread.

        Raises:
            NoElementException: If required elements are not found in response.
        """
        from .forum_post import ForumPostCollection

        # Get first page to determine total pages
        first_page_posts = self.get_posts(page=1)

        # Get total pages from pager
        response = self.site.amc_request(
            [
                {
                    "t": self.id,
                    "pageNo": 1,
                    "moduleName": "forum/ForumViewThreadModule",
                }
            ]
        )[0]

        body = response.json()["body"]
        html = BeautifulSoup(body, "lxml")

        all_posts = list(first_page_posts)

        # Check for pager
        pager = html.select_one("div.pager")
        if pager is not None:
            # Get last page number
            pager_links = pager.select("a")
            if len(pager_links) >= 2:
                last_page_link = pager_links[-2]
                last_page = int(last_page_link.text.strip())

                # Get remaining pages
                for page_num in range(2, last_page + 1):
                    page_posts = self.get_posts(page=page_num)
                    all_posts.extend(page_posts)

        return ForumPostCollection(thread=self, posts=all_posts)

    def get_post_by_id(self, post_id: int) -> Optional["ForumPost"]:
        """
        Get a specific post by its ID directly using ForumViewThreadPostsModule.

        This method uses Wikidot's API to fetch a specific post without loading
        all posts, making it very efficient for large threads.

        Args:
            post_id: The ID of the post to retrieve.

        Returns:
            ForumPost | None: The post object if found, None otherwise.

        Raises:
            NoElementException: If required elements are not found in response.
        """
        from .forum_post import ForumPost

        try:
            # Use ForumViewThreadPostsModule to get the post directly
            response = self.site.amc_request(
                [
                    {
                        "postId": post_id,
                        "t": self.id,
                        "order": "",
                        "moduleName": "forum/ForumViewThreadPostsModule",
                    }
                ]
            )[0]

            body = response.json()["body"]
            html = BeautifulSoup(body, "lxml")

            # Parse posts from the response
            posts = []
            for post_elem in html.select("div.post"):
                post_id_elem = post_elem.get("id")
                if post_id_elem is None:
                    continue

                parsed_post_id_str = str(post_id_elem).removeprefix("post-")
                if not parsed_post_id_str.isdigit():
                    continue
                parsed_post_id = int(parsed_post_id_str)

                # Find the parent post-container
                post_container = post_elem.parent

                # Get title
                title_elem = post_container.select_one("div.title")
                title = title_elem.text.strip() if title_elem else ""

                # Get text
                text_elem = post_container.select_one("div.content")
                text = str(text_elem) if text_elem else ""

                # Get created_by
                user_elem = post_container.select_one("div.info span.printuser")
                if user_elem is None:
                    raise NoElementException("User element is not found.")
                created_by = user_parser(self.site.client, user_elem)

                # Get created_at
                odate_elem = post_container.select_one("div.info span.odate")
                if odate_elem is None:
                    raise NoElementException("Odate element is not found.")
                created_at = odate_parser(odate_elem)

                # Get edited info if exists
                edited_by = None
                edited_at = None
                edit_info_elem = post_container.select_one("div.changes")
                if edit_info_elem:
                    edited_user_elem = edit_info_elem.select_one("span.printuser")
                    edited_odate_elem = edit_info_elem.select_one("span.odate")
                    if edited_user_elem and edited_odate_elem:
                        edited_by = user_parser(self.site.client, edited_user_elem)
                        edited_at = odate_parser(edited_odate_elem)

                # Get parent post ID if exists
                parent_post_id_val = None
                if post_container is not None:
                    parent_container = post_container.find_parent("div", class_="post-container")
                    if parent_container is not None:
                        parent_container_id = parent_container.get("id")
                        if parent_container_id:
                            parent_id_str = str(parent_container_id).removeprefix("fpc-")
                            if parent_id_str.isdigit():
                                parent_post_id_val = int(parent_id_str)

                post = ForumPost(
                    thread=self,
                    id=parsed_post_id,
                    title=title,
                    text=text,
                    element=post_elem,
                    created_by=created_by,
                    created_at=created_at,
                    edited_by=edited_by,
                    edited_at=edited_at,
                    _parent_id=parent_post_id_val,
                )

                posts.append(post)

            # Find and return the requested post
            for post in posts:
                if post.id == post_id:
                    return post

            return None

        except Exception:
            # Fallback to searching through pages if the module doesn't work
            return None
