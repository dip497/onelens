package com.acme.app.api;

import com.acme.app.api.dto.CreateOrderRequest;
import com.acme.app.api.dto.OrderResponse;
import com.acme.app.common.OrderStatus;
import com.acme.app.domain.Order;
import com.acme.app.service.OrderService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * Second REST controller — endpoints under /api/orders. Adds a @RequestParam
 * variant (GET /api/orders?status=PLACED) so the endpoint collector handles
 * query-param binding in addition to path + body.
 */
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public OrderResponse place(@Valid @RequestBody CreateOrderRequest req) {
        Order o = orderService.placeOrder(req.customerEmail(), req.total());
        return new OrderResponse(o.getId(), o.getCustomer().getEmail(), o.getStatus().name(), o.getTotal());
    }

    @GetMapping
    public List<OrderResponse> byStatus(@RequestParam OrderStatus status) {
        return orderService.findByStatus(status).stream()
            .map(o -> new OrderResponse(o.getId(), o.getCustomer().getEmail(), o.getStatus().name(), o.getTotal()))
            .toList();
    }
}
