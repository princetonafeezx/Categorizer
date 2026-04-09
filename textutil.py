# Import annotations from the future to allow for postponed evaluation of type hints
from __future__ import annotations

# Define a function to normalize and clean input strings for consistent comparison
def clean_text(text: str) -> str:
    # Initialize an empty list to store characters or replacement spaces
    parts: list[str] = []
    # Iterate through each character of the lowercase version of the input (handling None with an empty string)
    for char in (text or "").lower():
        # Check if the character is alphanumeric (a letter or a number)
        if char.isalnum():
            # If it is alphanumeric, append the character to the list
            parts.append(char)
        else:
            # If it is a special character or punctuation, append a space instead
            parts.append(" ")
    # Join the characters back into a string, split by whitespace to remove duplicates, and rejoin with single spaces
    return " ".join("".join(parts).split())    

# Define a private helper function to calculate the Levenshtein distance (edit distance) between two strings
def _levenshtein_distance(left: str, right: str) -> int:
    # If the strings are identical, the edit distance is zero
    if left == right:
        return 0
    # If the left string is empty, the distance is the full length of the right string (all insertions)
    if not left:
        return len(right)
    # If the right string is empty, the distance is the full length of the left string (all deletions)
    if not right:
        return len(left)

    # Initialize the first row of the matrix representing distances from an empty 'left' string
    previous_row = list(range(len(right) + 1))
    # Loop through each character in the 'left' string, starting the index at 1
    for left_index, left_char in enumerate(left, start=1):
        # Start a new row for the current character in 'left', initializing with the deletion cost
        current_row = [left_index]
        # Loop through each character in the 'right' string, starting the index at 1
        for right_index, right_char in enumerate(right, start=1):
            # Calculate the cost of inserting a character
            insert_cost = current_row[right_index - 1] + 1
            # Calculate the cost of deleting a character
            delete_cost = previous_row[right_index] + 1
            # Calculate the cost of replacing a character (0 if they match, 1 if they differ)
            replace_cost = previous_row[right_index - 1] + (0 if left_char == right_char else 1)
            # Append the minimum of these three costs to the current row to find the optimal path
            current_row.append(min(insert_cost, delete_cost, replace_cost))
        # Move to the next row by updating the previous row reference
        previous_row = current_row
    # Return the last element of the final row, which represents the total Levenshtein distance
    return previous_row[-1]

# Define a function to determine how similar two strings are, returning a value between 0.0 and 1.0
def similarity_ratio(left: str, right: str) -> float:
    # Clean and normalize the left string using the helper function defined above
    left = clean_text(left)
    # Clean and normalize the right string using the helper function defined above
    right = clean_text(right)
    # If both strings are empty after cleaning, consider them a perfect match
    if not left and not right:
        return 1.0
    # If only one string is empty, there is no similarity
    if not left or not right:
        return 0.0
    # If both strings are exactly the same, return a perfect similarity score
    if left == right:
        return 1.0
    # Check if one string is a substring of the other (e.g., "Amazon" in "Amazon MKTP")
    if left in right or right in left:
        # Get the length of the shorter string
        shorter = min(len(left), len(right))
        # Get the length of the longer string
        longer = max(len(left), len(right))
        # Return the ratio of their lengths as the similarity score
        return shorter / longer
    # Calculate the actual edit distance between the two strings
    distance = _levenshtein_distance(left, right)
    # Determine the length of the longest string to use as a denominator for normalization
    largest = max(len(left), len(right))
    # Calculate and return the ratio, ensuring the result is not negative
    return max(0.0, 1.0 - (distance / largest))