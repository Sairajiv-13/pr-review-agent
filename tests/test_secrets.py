from pr_review.providers import find_secret_kinds


def test_aws_key_hit():
    assert "AWS access key id" in find_secret_kinds(
        'key = "AKIAIOSFODNN7EXAMPLE"'
    )


def test_asia_session_key_hit():
    assert "AWS access key id" in find_secret_kinds("ASIA1234567890ABCDEF")


def test_private_key_hit():
    assert "private key block" in find_secret_kinds(
        "-----BEGIN RSA PRIVATE KEY-----"
    )
    assert "private key block" in find_secret_kinds(
        "-----BEGIN PRIVATE KEY-----"
    )


def test_hardcoded_assignment_hit():
    kinds = find_secret_kinds('api_key = "sk-live-9f8e7d6c5b4a3210"')
    assert "hardcoded credential assignment" in kinds


def test_bearer_literal_hit():
    assert "bearer token literal" in find_secret_kinds(
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789"
    )


def test_env_lookup_is_clean():
    assert find_secret_kinds('api_key = os.environ["API_KEY"]') == []
    assert find_secret_kinds('token = os.getenv("TOKEN", "")') == []


def test_short_value_is_clean():
    assert find_secret_kinds('password = "short"') == []


def test_plain_words_are_clean():
    assert find_secret_kinds("# the password field is required") == []
    assert find_secret_kinds('secret_sauce = "tomato and basil"') == []
