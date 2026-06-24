package com.onelens.fixture;

/**
 * Minimal fixture class for headless-export verification. The export must
 * surface this as a Class node with a greet() Method node, and a CALLS edge
 * from Greeter.main → Greeter.greet.
 */
public class Greeter {

    private final String name;

    public Greeter(String name) {
        this.name = name;
    }

    public String greet() {
        return "hello, " + name;
    }

    public static void main(String[] args) {
        Greeter g = new Greeter("onelens");
        // Call edge: main → greet. CallGraphCollector should emit CALLS.
        System.out.println(g.greet());
    }
}
