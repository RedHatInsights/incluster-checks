"""Example usage of the profile loader."""

from profiles.loader import ProfileLoader
from profiles.profile import Profiles


def main():
    """Demonstrate profile loading and dependency resolution."""
    # Create a Profiles instance
    profile = Profiles()

    # Load configuration into the instance
    ProfileLoader.load(profile)

    # Example 1: Nice print using str()
    print(profile)

    print("\n" + "=" * 60)

    # Example 2: Access nvidia profile (includes all transitive dependencies)
    profile_name = "nvidia"
    print(f"\nProfile '{profile_name}' includes (flat):")
    print(f"  {sorted(profile[profile_name])}")
    print("\nThis includes 'ai' and all its dependencies: 'ai-base', 'gpu', 'general'")

    print("\n" + "=" * 60)

    # Example 3: all includes everything
    profile_name = "all"
    print(f"\nProfile '{profile_name}' includes (flat):")
    print(f"  {sorted(profile[profile_name])}")

    print("\n" + "=" * 60)

    # Example 4: Test error handling with helpful message
    print("\nTesting error handling for non-existent profile:")
    print("Trying to access profile['does_not_exist']...\n")
    try:
        profile["does_not_exist"]
    except KeyError as e:
        print(f"KeyError caught with helpful message:\n{e}")

    print("\n" + "=" * 60)

    # Example 5: Using repr()
    print(f"\nUsing repr(): {repr(profile)}")

    print("\n" + "=" * 60)
    print("\nNotes:")
    print("- Create a Profiles() instance and pass it to ProfileLoader.load()")
    print("- Dependencies are resolved at load time into flat sets")
    print("- Circular dependencies are detected and raise ValueError")
    print("- Use str(profile) or print(profile) for nice formatting")
    print("- Accessing non-existent profiles shows all available options")


if __name__ == "__main__":
    main()
