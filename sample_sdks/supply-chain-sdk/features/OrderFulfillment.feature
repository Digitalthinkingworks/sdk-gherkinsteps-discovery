Feature: Order Fulfilment Processing

  @ShipOrder
  Scenario Outline: Successfully ship a customer order
    Given a confirmed order "<order_id>" exists in the system
    When the warehouse team processes the shipment at "<warehouse>"
    Then the order status should be "<status>"
    And the tracking number should be generated

    Examples:
      | order_id | warehouse | status  |
      | ORD-001  | Hub-A     | Shipped |
      | ORD-002  | Hub-B     | Shipped |

  @HoldOrder
  Scenario Outline: Place an order on hold pending review
    Given a confirmed order "<order_id>" is awaiting fulfilment
    When a hold is placed for reason "<reason>"
    Then the order status should change to "On Hold"
    And the customer should be notified

    Examples:
      | order_id | reason          |
      | ORD-003  | Payment review  |
      | ORD-004  | Address verify  |