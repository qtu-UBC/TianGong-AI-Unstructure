import tempfile
from unstructured.chunking.title import chunk_by_title
from unstructured.cleaners.core import (
    clean,
    group_broken_paragraphs,
)
from unstructured.documents.elements import Footer, Header, Image, CompositeElement, Table
from unstructured.partition.auto import partition
from tools.vision import vision_completion
import pandas as pd
import re
from typing import List

"""
Define helper functions
"""
# function to check if a string contains HTML tags
def contains_html(text) -> bool:
    # Regular expression pattern to detect typical HTML tags
    html_pattern = re.compile('<.*?>')
    return bool(html_pattern.search(text))

# function to convert a table from html format to dataframe
def html_to_table(html_string: str) -> pd.DataFrame:
    """
    Converts an HTML string with table data to a pandas DataFrame.

    :param html_string: String containing HTML data.
    :return: A pandas DataFrame
    """
    try:
        # Parse HTML string and convert tables to DataFrames
        table = pd.read_html(html_string)[0] # pd.read_html reads HTML tables into a list of DataFrame objects. 
                                            # But in this case, we will only have one table per html_string

        return table
    except ValueError as e:
        # Return an empty list if no tables are found or if an error occurs
        print(f"No tables found or error in parsing: {e}")
        return []


pdf_name = "table example for unstructured.pdf"

min_image_width = 250
min_image_height = 270

elements = partition(
    filename=pdf_name,
    pdf_extract_images=True,
    pdf_image_output_dir_path=tempfile.gettempdir(),
    skip_infer_table_types=["jpg", "png", "xls", "xlsx"],
    strategy="hi_res",
)

filtered_elements = [
    element
    for element in elements
    if not (isinstance(element, Header) or isinstance(element, Footer))
]

for element in filtered_elements:
    if element.text != "":
        element.text = group_broken_paragraphs(element.text)
        element.text = clean(
            element.text,
            bullets=False,
            extra_whitespace=True,
            dashes=False,
            trailing_punctuation=False,
        )
    elif isinstance(element, Image):
        point1 = element.metadata.coordinates.points[0]
        point2 = element.metadata.coordinates.points[2]
        width = abs(point2[0] - point1[0])
        height = abs(point2[1] - point1[1])
        if width >= min_image_width and height >= min_image_height:
            # generate text from the image
            element.text = vision_completion(element.metadata.image_path)

chunks = chunk_by_title(
    elements=filtered_elements,
    multipage_sections=True,
    combine_text_under_n_chars=0,
    new_after_n_chars=None,
    max_characters=4096,
)

text_list = []
for chunk in chunks:
    if isinstance(chunk, CompositeElement):
        text = chunk.text
        text_list.append(text)
    elif isinstance(chunk, Table):
        if text_list:
            text_list[-1] = text_list[-1] + "\n" + chunk.metadata.text_as_html
        else:
            text_list.append(chunk.metadata.text_as_html)
result_list = []

for text in text_list:
    split_text = text.split("\n\n", 1)
    if len(split_text) == 2:
        title, body = split_text
    else:
        # Handle cases where the split does not result in two parts
        result_list.append({'title': 'Unknown', 'body': text})

# for result in result_list:
#     print(result)
#     print("\n\n" + "-" * 80)
#     input()

# Convert the result_list to a DataFrame
df = pd.DataFrame(result_list)
# print(df)

# identify the cells with html tags (i.e., extracted tables)
# apply the function to each row in the 'body' column and add a new column 'contains_html'
df['contains_html'] = df['body'].apply(contains_html)

# Display the modified DataFrame
print(df)

# reformat the tables (from html to dataframe)
df_table_only = df[df['contains_html']==True] 
table_dfs = df_table_only['body'].apply(html_to_table)

# Export the tables into an xlsx file
with pd.ExcelWriter('output_tables.xlsx') as writer:
    for i,table_df in enumerate(table_dfs):
        table_df.to_excel(writer, sheet_name=f"extracted_tab_{i}", index=False)
