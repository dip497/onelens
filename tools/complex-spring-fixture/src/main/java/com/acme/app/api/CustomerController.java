package com.acme.app.api;

import com.acme.app.api.dto.CreateCustomerRequest;
import com.acme.app.api.dto.CustomerResponse;
import com.acme.app.domain.Customer;
import com.acme.app.service.CustomerService;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * REST controller for customers — exercises endpoint detection with:
 *  - class-level @RequestMapping("/api/customers")
 *  - @PostMapping + @GetMapping method mappings
 *  - @Valid + @RequestBody (validation param)
 *  - constructor injection of CustomerService
 * Endpoints expected:
 *   POST /api/customers, GET /api/customers, GET /api/customers/{email}
 */
@RestController
@RequestMapping("/api/customers")
public class CustomerController {

    private final CustomerService customerService;

    public CustomerController(CustomerService customerService) {
        this.customerService = customerService;
    }

    @PostMapping
    public ResponseEntity<CustomerResponse> create(@Valid @RequestBody CreateCustomerRequest req) {
        Customer c = customerService.create(req.name(), req.email());
        return ResponseEntity.ok(new CustomerResponse(c.getId(), c.getName(), c.getEmail()));
    }

    @GetMapping
    public List<CustomerResponse> list() {
        return customerService.findAll().stream()
            .map(c -> new CustomerResponse(c.getId(), c.getName(), c.getEmail()))
            .toList();
    }

    @GetMapping("/{email}")
    public CustomerResponse getByEmail(java.util.Map<String, String> vars) {
        Customer c = customerService.findByEmail(vars.get("email"));
        return new CustomerResponse(c.getId(), c.getName(), c.getEmail());
    }
}
