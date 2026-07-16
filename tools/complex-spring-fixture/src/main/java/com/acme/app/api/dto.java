package com.acme.app.api;

/**
 * Request/response DTOs as Java records — exercises record-type detection in
 * the class/type collector (records are a distinct PSI kind). The controller
 * layer takes these as @RequestBody params and returns them.
 */
public final class dto {

    private dto() {}

    public record CreateCustomerRequest(String name, String email) {}

    public record CustomerResponse(Long id, String name, String email) {}

    public record CreateOrderRequest(String customerEmail, Double total) {}

    public record OrderResponse(Long id, String customerEmail, String status, Double total) {}
}
