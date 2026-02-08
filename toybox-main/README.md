# toybox

## Prepare Python virtual environment

    #### Create a virtual environment (first time only)
    $ cd toybox        # this directory
    $ python3 -m venv venv

    #### Enter the virtual environment (every time start using this toybox)
    $ source venv/bin/activate

    #### Install Python packages (first time and when adding new packages)
    $ pip install -r requirements.txt

    #### Exit the virual environment (every time after using this toybox)
    $ deactivate

## SAT CLI

Multiple developer tools use the SAT (WebSec) authentication https://sat-ng.comcast.com/ .
This CLI provides a simple use of SAT access token generation.

    #### Register an SAT account with a label of your choice
    $ python websec.py my_label --url https://sat-prod.codebig2.net/v2/ws/token.oauth2 --id ID --secret SECRET --scope "genome:nql:cm:read genome:nql:read genome:nql:cm:write"

    #### Retrieve a valid access token for the label
    $ python websec.py my_label

    #### Show the token in "bearer" format (for Genome NQL Playground, etc)
    $ python websec.py my_label --bearer

    #### Show the registered info for the label
    $ python websec.py my_label --show

## Thanos CLI

    #### Register SAT clients for "thanos-dev" and "thanos-prod".
    $ python websec.py thanos-dev --url https://sat-stg.codebig2.net/v2/ws/token.oauth2 --id ID --secret SECRET --scope ngan:telemetry:thanosapi

    $ python websec.py thanos-prod --url https://sat-prod.codebig2.net/v2/ws/token.oauth2 --id ID --secret SECRET --scope ngan:telemetry:thanosapi

    $ python websec.py thanos-dev
    $ python websec.py thanos-prod

    #### Use Thanos preprod/dev
    $ python thanos.py K_RpdInfo

    #### Use Thanos prod, with indented output and a filter
    $ python thanos.py --prod --indent K_RpdInfo ppod_name=CONCPP101

    #### Get values of recent 10 minutes
    $ python thanos.py --indent --duration 10m K_CmRegStatus_RegStatus rpdName=DCXIHN0004

## Genome CLI

    #### Register an SAT client for genome
    $ python websec.py genome --url https://sat-prod.codebig2.net/v2/ws/token.oauth2 --id ID --secret SECRET --scope "genome:nql:cm:read genome:nql:cmts:read genome:nql:read genome:nql:cm:write"

    ### Query the modem info of a device
    $ python genome_modem.py 00:00:00:00:00:00 --sysprops

## iHAT Test CLI

    #### Register an SAT client for iHAT API
    $ python websec.py ihat ... --scope "ihat:access ihat:read ihat:read:details ihat:read:inconclusive ihat:mutate:settosubsplit ihat:query:ondemandihattest"

    #### Get previous test results (for the account with modem 14:c0:3e:aa:bb:cc)
    $ python ihat_test.py get 14:c0:3e:aa:bb:cc

    #### Request to run a test (for the account with modem 14:c0:3e:aa:bb:cc and STB 14:c0:3e:dd:ee:ff)
    $ python ihat_test.py run 14:c0:3e:aa:bb:cc 14:c0:3e:dd:ee:ff

## iHAT Subsplit Exclusion List CLI

    #### Show the current modems on the subsplit exclusion list
    $ python ihat_subsplit.py get

    #### Add modems to the subsplit exclusion list
    $ python ihat_subsplit.py to_subsplit 00:00:00:00:00:00 11:11:11:11:11:11

    #### Remove modems from the subsplit exclusion list
    $ python ihat_subsplit.py to_midsplit 00:00:00:00:00:00 11:11:11:11:11:11

## STB Status CLI

`stb_health.py` requires a client ID with the `deviceservices:stb:health` scope paired with a CodeBig2 credential for the `deviceservices-stb-health-prod` service.

`stb_video.py` requires a client ID with the `dmetrix:video:read` scope paired with a CodeBig2 credential for the `deviceservices-video-prod` service.

    #### Register SAT clients
    $ python websec.py stb-health ... --scope deviceservices:stb:health
    $ python websec.py stb-video ... --scope dmetrix:video:read

    #### Query the STB's health by its MAC address
    $ python stb_health.py 22:22:22:22:22:22

    #### Query the STB video tuner status
    $ python stb_video.py 22:22:22:22:22:22

    #### Query the STB video tuner status and other details
    $ python stb_video.py 22:22:22:22:22:22 --details

# References

* [SAT Developer Portal](https://sat-ng.comcast.com/)
* [Prometheus HTTP API](https://prometheus.io/docs/prometheus/latest/querying/api/)
* [Telemetry API Access](https://etwiki.sys.comcast.net/pages/viewpage.action?spaceKey=NGAN&title=Telemetry+%28Thanos%29+API+Access)
* [CodeBig2](https://selfservice.codebig2.net/)
* [Genome NQL Playground](https://nql.genome.comcast.com)
* [iHAT API Playground](https://api.ihat.comcast.com)
* [deviceservice-stb-health](https://etwiki.sys.comcast.net/display/OSSTOOLS/deviceservice-stb-health+Service)
* [deviceservices-video](https://etwiki.sys.comcast.net/display/OSSTOOLS/deviceservices-video)
* [WebSec Portal](https://websecdevportal.cable.comcast.com/portal/#/home)
