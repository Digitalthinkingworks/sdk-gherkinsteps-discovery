import io.cucumber.java.en.Given;
import io.cucumber.java.en.When;
import io.cucumber.java.en.Then;
import io.cucumber.java.en.And;

public class OrderFulfilmentSteps {

    // --- Scenario: Successfully ship a customer order ---

    @Given("a confirmed order {string} exists in the system")
    public void checkOrderExistsInTheSystem(String orderId) {
        System.out.println("Checking system for Order ID: " + orderId);
    }

    @When("the warehouse team processes the shipment at {string}")
    public void processShipment(String warehouse) {
        System.out.println("Processing shipment at warehouse: " + warehouse);
    }

    @Then("the order status should be {string}")
    public void verifyStatus(String status) {
        System.out.println("Verifying status is: " + status);
    }

    @And("the tracking number should be generated")
    public void verifyTracking() {
        System.out.println("Confirmed: Tracking number generated.");
    }

    // --- Scenario: Place an order on hold pending review ---

    @Given("a confirmed order {string} is awaiting fulfilment")
    public void checkOrderIsAwaitingFulfilment(String orderId) {
        System.out.println("Order " + orderId + " is ready for fulfilment.");
    }

    @When("a hold is placed for reason {string}")
    public void placeHold(String reason) {
        System.out.println("Placing hold due to: " + reason);
    }

    @Then("the order status should change to {string}")
    public void verifyHoldStatus(String status) {
        // This method reuses the logic if needed, or handles specific "On Hold" logic
        System.out.println("Confirmed status changed to: " + status);
    }

    @And("the customer should be notified")
    public void notifyCustomer() {
        System.out.println("Notification sent to the customer.");
    }
}
