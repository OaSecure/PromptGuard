from radon.complexity import cc_visit


def complexity(source: str) -> int:
    return cc_visit(source)[0].complexity


def test_new_function_complexity_b_or_lower_passes():
    assert complexity("def f(x):\n    if x:\n        return 1\n    return 0\n") <= 10


def test_new_function_complexity_c_or_higher_is_rejected_by_threshold():
    branches = "".join(f"    if x == {index}: return {index}\n" for index in range(11))
    assert complexity("def f(x):\n" + branches + "    return -1\n") > 10
