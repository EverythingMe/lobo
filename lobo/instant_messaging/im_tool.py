from lobo import configuration, nop_driver

im_tool = configuration.get_config('driver:im')
if im_tool == 'hipchat':
    import hipchat_tool as im_driver
else:
    im_driver = nop_driver.NopDriver()

def tool_entry():
    parser = ToolkitBase([im_driver.TestConnection, im_driver.SendMessage])
    parser.parse()

send_message = im_driver.SendMessage()
test_connection = im_driver.TestConnection()

if __name__ == "__main__":
    tool_entry()
