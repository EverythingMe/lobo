from lobo import configuration, nop_driver

cr_tool = configuration.get_config('driver:builder')
if cr_tool == 'jenkins':
    import jenkins_tool as builder_driver
else:
    builder_driver = nop_driver.NopDriver()


def tool_entry():
    parser = ToolkitBase([builder_driver.RunBuild, builder_driver.TestConnection])
    parser.parse()

run_build = builder_driver.RunBuild()
test_connection = builder_driver.TestConnection()

if __name__ == "__main__":
    tool_entry()
