package com.livestock.platform.system;

public record DependencyStatus(String status) {

    public static DependencyStatus up() {
        return new DependencyStatus("UP");
    }

    public static DependencyStatus down() {
        return new DependencyStatus("DOWN");
    }
}
