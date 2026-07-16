package com.onelens.fixture;

/**
 * Second fixture class — extends nothing, but Greeter-style call edge from
 * Counter.increment → Counter.current gives the call-graph collector a
 * second intra-class edge, and lets the inheritance collector emit zero
 * edges cleanly (no EXTENDS/IMPLEMENTS). Keeps the fixture minimal while
 * exercising more than one method.
 */
public class Counter {

    private int count;

    public int increment() {
        count = count + 1;
        return current();
    }

    public int current() {
        return count;
    }
}
