import unittest

from x_workflows_collector.collector import extract_post_from_article_data


class CollectorMappingTests(unittest.TestCase):
    def test_post_preserves_requested_profile_for_reposts(self):
        post = extract_post_from_article_data(
            {
                "datetime": "2026-08-11T02:00:54.000Z",
                "status_path": "/BleepinComputer/status/1869489454731194815",
                "tweet_text": "Example repost",
                "images": [],
                "card_type": None,
            },
            "@serghei",
        )

        self.assertIsNotNone(post)
        self.assertEqual(post.requested_handle, "serghei")
        self.assertEqual(post.handle, "BleepinComputer")


if __name__ == "__main__":
    unittest.main()
