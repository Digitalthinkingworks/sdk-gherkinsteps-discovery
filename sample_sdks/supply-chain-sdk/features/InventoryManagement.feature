Feature: Inventory Management
  The system should allow users to manage inventory efficiently.
  SDKs provide reusable scenarios to reduce testing effort and improve standardization.

  Background:
    Given the inventory system is initialized
    And the user is logged in with valid credentials

  @AddItem
  Scenario Outline: Add a new item to inventory
    When the user adds an item "<item_name>" with quantity "<quantity>"
    Then the inventory should contain "<item_name>" with quantity "<quantity>"

    Examples:
      | item_name | quantity |
      | Laptop    | 10       |
      | Mouse     | 25       |

  @UpdateItem
  Scenario Outline: Update item quantity
    Given an item "<item_name>" exists with quantity "<old_quantity>"
    When the user updates the quantity of "<item_name>" to "<new_quantity>"
    Then the inventory should show "<item_name>" with quantity "<new_quantity>"

    Examples:
      | item_name | old_quantity | new_quantity |
      | Laptop    | 10           | 15           |
      | Mouse     | 25           | 30           |

  @RemoveItem
  Scenario Outline: Remove an item from inventory
    Given an item "<item_name>" exists with quantity "<quantity>"
    When the user removes "<item_name>" from inventory
    Then the inventory should not contain "<item_name>"

    Examples:
      | item_name | quantity |
      | Laptop    | 10       |
      | Keyboard  | 5        |

  @SearchItem
  Scenario Outline: Search for an existing item
    Given an item "<item_name>" exists with quantity "<quantity>"
    When the user searches for "<item_name>"
    Then the system should return "<item_name>" with quantity "<quantity>"

    Examples:
      | item_name | quantity |
      | Laptop    | 10       |
      | Mouse     | 25       |

  @SearchItemNegative
  Scenario Outline: Search for a non-existing item
    When the user searches for "<item_name>"
    Then the system should indicate "<item_name>" is not found

    Examples:
      | item_name |
      | Tablet    |
      | Monitor   |

  @DuplicateItem
  Scenario Outline: Prevent duplicate item addition
    Given an item "<item_name>" exists with quantity "<quantity>"
    When the user tries to add "<item_name>" again
    Then the system should prevent duplicate entry

    Examples:
      | item_name | quantity |
      | Laptop    | 10       |
      | Mouse     | 25       |

  @NegativeQuantity
  Scenario Outline: Validate negative quantity entry
    When the user tries to add an item "<item_name>" with quantity "<quantity>"
    Then the system should reject the entry with an error message

    Examples:
      | item_name | quantity |
      | Mouse     | -5       |
      | Keyboard  | -10      |

  @ZeroQuantity
  Scenario Outline: Validate zero quantity entry
    When the user tries to add an item "<item_name>" with quantity "<quantity>"
    Then the system should reject the entry with an error message

    Examples:
      | item_name | quantity |
      | Keyboard  | 0        |
      | Monitor   | 0        |

  @ViewAllItems
  Scenario Outline: View all items in inventory
    Given items "<item1>" and "<item2>" exist in inventory
    When the user views all items
    Then the system should display "<item1>" and "<item2>"

    Examples:
      | item1  | item2  |
      | Laptop | Mouse  |
      | Pen    | Paper  |

  @LowStock
  Scenario Outline: Track low stock items
    Given an item "<item_name>" exists with quantity "<quantity>"
    And the low stock threshold is "<threshold>"
    When the user views low stock items
    Then the system should list "<item_name>" as low stock

    Examples:
      | item_name | quantity | threshold |
      | Laptop    | 2        | 5         |
      | Mouse     | 3        | 10        |

  @ExportReport
  Scenario Outline: Export inventory report
    Given items exist in inventory
    When the user exports the inventory report in "<format>"
    Then the system should generate a report file with all items in "<format>"

    Examples:
      | format |
      | CSV    |
      | PDF    |

  @ImportData
  Scenario Outline: Import inventory data
    When the user imports a valid inventory file "<file_name>"
    Then the system should update inventory with the imported data

    Examples:
      | file_name       |
      | inventory.csv   |
      | inventory.json  |