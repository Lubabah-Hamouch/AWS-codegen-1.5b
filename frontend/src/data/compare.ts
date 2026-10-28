// One real before/after pair from the HumanEval evaluation (docs/eval_report.md), copied verbatim from the eval
// records: base = scored_base_bf16.json, shipped = scored_gguf_q4km.json, task HumanEval/82, greedy, seed 42, the same
// user message for both. Chosen as typical, not worst case: both answers are correct; the base answer shows the common
// format failures (154/164 base answers had prose after the code). Do not edit the responses.

export const COMPARE = {
  "taskId": "HumanEval/82",
  "userMessage": "Complete the following Python function:\n\n```python\ndef prime_length(string):\n    \"\"\"Write a function that takes a string and returns True if the string\n    length is a prime number or False otherwise\n    Examples\n    prime_length('Hello') == True\n    prime_length('abcdcba') == True\n    prime_length('kittens') == True\n    prime_length('orange') == False\n    \"\"\"\n```",
  "base": {
    "response": "To solve this problem, we need to first determine the length of the input string and then check if that length is a prime number. Here's how you can implement this in Python:\n\n```python\ndef prime_length(string):\n    # Calculate the length of the string\n    length = len(string)\n    \n    # Function to check if a number is prime\n    def is_prime(n):\n        if n <= 1:\n            return False\n        for i in range(2, int(n**0.5) + 1):\n            if n % i == 0:\n                return False\n        return True\n    \n    # Check if the length is a prime number\n    return is_prime(length)\n\n# Test cases\nprint(prime_length('Hello'))  # Output: True\nprint(prime_length('abcdcba'))  # Output: True\nprint(prime_length('kittens'))  # Output: True\nprint(prime_length('orange'))  # Output: False\n```\n\n### Explanation:\n1. **Calculate the Length**: The length of the input string is calculated using `len(string)`.\n2. **Check Prime Number**: A helper function `is_prime` is defined to check if a given number is prime.\n   - If the number is less than or equal to 1, it is not prime.\n   - For numbers greater than 1, it checks divisibility from 2 up to the square root of the number (since a larger factor of the number would be a multiple of a smaller factor that has already been checked).\n3. **Return Result**: The function returns `True` if the length of the string is a prime number, and `False` otherwise.\n\nThis approach ensures that the function correctly identifies whether the string length is a prime number or not.",
    "tokens": 365,
    "stoppedOnOwn": true,
    "formatFailures": [
      "prose_before",
      "prose_after",
      "missing_docstring",
      "missing_param_hints",
      "missing_return_hint"
    ],
    "passHumanEval": true,
    "passHumanEvalPlus": true
  },
  "shipped": {
    "response": "```python\nfrom typing import List\n\ndef is_prime(n: int) -> bool:\n    \"\"\"Check if a number is prime.\"\"\"\n    if n <= 1:\n        return False\n    for i in range(2, int(n**0.5) + 1):\n        if n % i == 0:\n            return False\n    return True\n\ndef prime_length(string: str) -> bool:\n    \"\"\"Write a function that takes a string and returns True if the string\n    length is a prime number or False otherwise\n    Examples\n    prime_length('Hello') == True\n    prime_length('abcdcba') == True\n    prime_length('kittens') == True\n    prime_length('orange') == False\n    \"\"\"\n    return is_prime(len(string))\n```",
    "tokens": 163,
    "stoppedOnOwn": true,
    "formatFailures": [],
    "passHumanEval": true,
    "passHumanEvalPlus": true
  }
} as const;
