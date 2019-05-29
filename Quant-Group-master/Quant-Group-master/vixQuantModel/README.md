# Quantopian

## Rules of the road

Create a new directory for each algorithm and add a README.md file that
describes the approach. In the README file add the following sections:

1. An overview of the approach - describe the algorithm
2. A review of what worked and what didn't work - created as the last step
3. Links to background information - provide contextual information
4. Charts, or links to charts, that show results

Let's standardize on lower-case file names and use a hyphen (-) for word
seperation, for example, test-long-short-001.py.

Use GitFlow when making changes:

1. Create a new branch
2. Open a new issue
3. Commit code to the branch
4. Create a pull request
5. Get approvals
6. Merge into master
7. Delete the branch

## Quantopian notes

About 90% of algorithm development is spent in "research." Once an algorithm is
developed it can be moved to a pipeline for more extensive analysis.
